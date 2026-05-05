from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Candidate, Evaluation, Position
from app.schemas import CurrentUser
from app.workflows.runner import mark_evaluation_failed, run_candidate_evaluation
from app.workflows.hashing import save_evaluation_hashes

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


class EvaluationStartResponse(BaseModel):
    status: str
    evaluation_id: str


class EvaluationGetResponse(BaseModel):
    status: str
    card: dict | None = None
    error: str | None = None
    is_stale: bool = False
    stale_reason: str | None = None


def _set_processing(db: Session, candidate_id: str) -> None:
    row = db.query(Evaluation).filter(Evaluation.candidate_id == candidate_id).first()
    if row is None:
        return
    row.status = "processing"
    row.error_message = ""
    row.updated_by = "workflow"
    db.commit()


def _run_evaluation_task(candidate_id: str) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        _set_processing(db, candidate_id)
        card = run_candidate_evaluation(db, candidate_id)

        row = db.query(Evaluation).filter(Evaluation.candidate_id == candidate_id).first()
        if row is not None:
            row.status = "completed"
            row.recommendation = str(card.get("recommendation", ""))
            row.overall_score = float(card.get("overall_score", 0.0) or 0.0)
            row.must_have_score = float(card.get("must_have_score", 0.0) or 0.0)
            row.evaluation_json = json.dumps(card, ensure_ascii=True)
            row.error_message = ""
            row.model_used = str(card.get("model_used", ""))
            row.schema_version = str(card.get("schema_version", "1.0.0"))
            row.updated_at = datetime.utcnow()
            row.updated_by = "workflow"
            # Save current docs hashes and clear stale flag
            candidate_obj = db.query(Candidate).filter(Candidate.candidate_id == candidate_id).first()
            position_id = candidate_obj.position_id if candidate_obj else row.position_id
            save_evaluation_hashes(db, row, candidate_id, position_id)
            db.commit()
    except Exception as exc:
        mark_evaluation_failed(db, candidate_id, str(exc))
    finally:
        db.close()


def _candidate_for_owner(db: Session, candidate_id: str, owner_id: str):
    return (
        db.query(Candidate)
        .join(Position, Position.position_id == Candidate.position_id)
        .filter(Candidate.candidate_id == candidate_id, Position.owner_id == owner_id)
        .first()
    )


@router.post("/{candidate_id}", response_model=EvaluationStartResponse)
def start_evaluation(
    candidate_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> EvaluationStartResponse:
    candidate = _candidate_for_owner(db, candidate_id, current_user.user_id)
    if candidate is None and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="Candidate not found")

    existing = db.query(Evaluation).filter(Evaluation.candidate_id == candidate_id).first()
    now = datetime.utcnow()

    if existing is None:
        evaluation = Evaluation(
            evaluation_id=str(uuid4()),
            candidate_id=candidate_id,
            position_id=candidate.position_id if candidate else "",
            status="pending",
            created_at=now,
            updated_at=now,
            created_by=current_user.email,
            updated_by=current_user.email,
        )
        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)
        eval_id = evaluation.evaluation_id
    else:
        existing.status = "pending"
        existing.error_message = ""
        existing.updated_at = now
        existing.updated_by = current_user.email
        db.commit()
        eval_id = existing.evaluation_id

    background_tasks.add_task(_run_evaluation_task, candidate_id)
    return EvaluationStartResponse(status="pending", evaluation_id=eval_id)


@router.get("/{candidate_id}", response_model=EvaluationGetResponse)
def get_evaluation(
    candidate_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> EvaluationGetResponse:
    candidate = _candidate_for_owner(db, candidate_id, current_user.user_id)
    if candidate is None and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="Candidate not found")

    row = db.query(Evaluation).filter(Evaluation.candidate_id == candidate_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    parsed_card = None
    if row.evaluation_json:
        try:
            parsed_card = json.loads(row.evaluation_json)
        except json.JSONDecodeError:
            parsed_card = None

    return EvaluationGetResponse(
        status=row.status,
        card=parsed_card,
        error=row.error_message or None,
        is_stale=bool(row.is_stale),
        stale_reason=row.stale_reason,
    )
