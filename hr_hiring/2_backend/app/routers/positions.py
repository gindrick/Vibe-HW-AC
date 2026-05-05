from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user, get_db
from app.models import Candidate, CandidateDocument, Evaluation, Position, PositionDocument
from app.services.document_ingest import extract_text_from_payload, store_binary_file, store_text_file
from app.workflows.hashing import refresh_position_evals_staleness, save_evaluation_hashes
from app.schemas import (
    BatchUploadItem,
    BatchUploadResponse,
    CandidateDashboardItem,
    CandidateListItem,
    CurrentUser,
    DashboardStats,
    DocumentUploadResponse,
    PositionCandidatesResponse,
    PositionCreateRequest,
    PositionDashboardResponse,
    PositionDocumentSummary,
    PositionResponse,
    PositionsResponse,
)


def _doc_summary(doc: PositionDocument) -> PositionDocumentSummary:
    return PositionDocumentSummary(
        document_id=doc.document_id,
        file_name=doc.file_name,
        document_type=doc.document_type,
        is_text=doc.mime_type == "text/plain",
    )


def _to_response(item: Position) -> PositionResponse:
    return PositionResponse(
        position_id=item.position_id,
        owner_id=item.owner_id,
        title=item.title,
        description=item.description,
        status=item.status,
        salary_from=item.salary_from,
        salary_to=item.salary_to,
        salary_visible=bool(item.salary_visible),
        opened_at=item.opened_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        documents=[_doc_summary(d) for d in (item.documents or [])],
    )

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=PositionsResponse)
def list_positions(
    status: Literal["active", "archived", "all"] = Query(default="active"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PositionsResponse:
    query = db.query(Position).filter(Position.owner_id == current_user.user_id)
    if status != "all":
        query = query.filter(Position.status == status)

    records = query.order_by(Position.updated_at.desc()).all()
    return PositionsResponse(items=[_to_response(item) for item in records])


@router.post("", response_model=PositionResponse)
def create_position(
    payload: PositionCreateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PositionResponse:
    now = datetime.utcnow()
    position = Position(
        position_id=str(uuid4()),
        owner_id=current_user.user_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        status="active",
        salary_from=payload.salary_from,
        salary_to=payload.salary_to,
        salary_visible=payload.salary_visible,
        opened_at=payload.opened_at or now,
        created_at=now,
        updated_at=now,
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return _to_response(position)


@router.get("/{position_id}", response_model=PositionResponse)
def get_position(
    position_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PositionResponse:
    position = db.query(Position).filter(Position.position_id == position_id).first()
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    if current_user.role != "admin" and position.owner_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Position not found")
    return _to_response(position)


@router.delete("/{position_id}/documents/{document_id}")
def delete_position_document(
    position_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    position = db.query(Position).filter(Position.position_id == position_id).first()
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    if current_user.role != "admin" and position.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    doc = db.query(PositionDocument).filter(
        PositionDocument.document_id == document_id,
        PositionDocument.position_id == position_id,
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except Exception:
        pass

    db.delete(doc)
    db.commit()
    refresh_position_evals_staleness(db, position_id)
    return {"deleted": document_id}


@router.patch("/{position_id}/archive", response_model=PositionResponse)
def archive_position(
    position_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PositionResponse:
    position = (
        db.query(Position)
        .filter(Position.position_id == position_id, Position.owner_id == current_user.user_id)
        .first()
    )

    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")

    position.status = "archived"
    position.updated_at = datetime.utcnow()
    position.updated_by = current_user.email
    db.commit()
    db.refresh(position)

    return _to_response(position)


@router.get("/{position_id}/candidates", response_model=PositionCandidatesResponse)
def list_position_candidates(
    position_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PositionCandidatesResponse:
    position = db.query(Position).filter(Position.position_id == position_id).first()
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")

    if current_user.role != "admin" and position.owner_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Position not found")

    rows = (
        db.query(Candidate, Evaluation)
        .outerjoin(Evaluation, and_(Evaluation.candidate_id == Candidate.candidate_id))
        .filter(Candidate.position_id == position_id)
        .order_by(Candidate.created_at.desc())
        .all()
    )

    items = [
        CandidateListItem(
            candidate_id=candidate.candidate_id,
            full_name=candidate.full_name,
            email=candidate.email,
            external_ref=candidate.external_ref,
            profile_status=candidate.profile_status or "pending",
            profile_json=candidate.profile_json,
            evaluation_status=evaluation.status if evaluation else None,
            recommendation=evaluation.recommendation if evaluation and evaluation.recommendation else None,
            overall_score=float(evaluation.overall_score) if evaluation and evaluation.overall_score is not None else None,
            evaluation_json=evaluation.evaluation_json if evaluation else None,
            is_stale=bool(evaluation.is_stale) if evaluation else False,
            stale_reason=evaluation.stale_reason if evaluation else None,
        )
        for candidate, evaluation in rows
    ]

    return PositionCandidatesResponse(items=items)


def _extract_and_evaluate_task(candidate_id: str, position_id: str, created_by: str) -> None:
    """Background task: create evaluation record → run evaluation (profile extracted by evaluator LLM)."""
    from app.database import SessionLocal
    from app.workflows.runner import mark_evaluation_failed, run_candidate_evaluation

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        existing = db.query(Evaluation).filter(Evaluation.candidate_id == candidate_id).first()
        if existing is None:
            ev = Evaluation(
                evaluation_id=str(uuid4()),
                candidate_id=candidate_id,
                position_id=position_id,
                status="pending",
                created_at=now,
                updated_at=now,
                created_by=created_by,
                updated_by=created_by,
            )
            db.add(ev)
            db.commit()
        else:
            existing.status = "pending"
            existing.updated_at = now
            db.commit()

        ev_row = db.query(Evaluation).filter(Evaluation.candidate_id == candidate_id).first()
        if ev_row:
            ev_row.status = "processing"
            db.commit()

        card = run_candidate_evaluation(db, candidate_id)

        ev_row = db.query(Evaluation).filter(Evaluation.candidate_id == candidate_id).first()
        if ev_row:
            ev_row.status = "completed"
            ev_row.recommendation = str(card.get("recommendation", ""))
            ev_row.overall_score = float(card.get("overall_score", 0.0) or 0.0)
            ev_row.must_have_score = float(card.get("must_have_score", 0.0) or 0.0)
            ev_row.evaluation_json = json.dumps(card, ensure_ascii=True)
            ev_row.model_used = str(card.get("model_used", ""))
            ev_row.schema_version = str(card.get("schema_version", "1.0.0"))
            ev_row.updated_at = datetime.utcnow()
            ev_row.updated_by = "workflow"
            save_evaluation_hashes(db, ev_row, candidate_id, position_id)
            db.commit()
    except Exception as exc:
        mark_evaluation_failed(db, candidate_id, str(exc))
    finally:
        db.close()


@router.post("/{position_id}/upload", response_model=BatchUploadResponse)
async def batch_upload_candidates(
    position_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> BatchUploadResponse:
    """Upload N CV files at once — creates one candidate per file and auto-runs extract+evaluate."""
    position = db.query(Position).filter(Position.position_id == position_id).first()
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    if current_user.role != "admin" and position.owner_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Position not found")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    upload_root = Path(settings.upload_root)
    now = datetime.utcnow()
    result_items: list[BatchUploadItem] = []

    for upload_file in files:
        file_name = upload_file.filename or "cv.pdf"
        placeholder = f"_{Path(file_name).stem}"

        candidate = Candidate(
            candidate_id=str(uuid4()),
            position_id=position_id,
            full_name=placeholder,
            email="",
            profile_status="extracting",
            created_at=now,
            updated_at=now,
            created_by=current_user.email,
            updated_by=current_user.email,
        )
        db.add(candidate)
        db.flush()  # get candidate_id before commit

        payload_bytes = await upload_file.read()
        mime_type = upload_file.content_type or "application/octet-stream"
        file_path = store_binary_file(upload_root, "candidates", candidate.candidate_id, file_name, payload_bytes)
        extracted = extract_text_from_payload(payload_bytes, mime_type, file_name)

        doc = CandidateDocument(
            document_id=str(uuid4()),
            candidate_id=candidate.candidate_id,
            document_type="cv",
            file_name=file_name,
            file_path=str(file_path),
            mime_type=mime_type,
            extracted_text=extracted,
            is_processed=bool(extracted.strip()),
            created_at=now,
            updated_at=now,
            created_by=current_user.email,
            updated_by=current_user.email,
        )
        db.add(doc)

        result_items.append(BatchUploadItem(
            candidate_id=candidate.candidate_id,
            file_name=file_name,
            profile_status="extracting",
        ))

        background_tasks.add_task(
            _extract_and_evaluate_task,
            candidate.candidate_id,
            position_id,
            current_user.email,
        )

    db.commit()
    return BatchUploadResponse(candidates=result_items)


@router.post("/{position_id}/documents", response_model=DocumentUploadResponse)
async def upload_position_document(
    position_id: str,
    document_type: Literal["job_description", "supplementary"] = Form(...),
    file: UploadFile | None = File(default=None),
    text_content: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentUploadResponse:
    position = db.query(Position).filter(Position.position_id == position_id).first()
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")

    if current_user.role != "admin" and position.owner_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Position not found")

    if file is None and not (text_content and text_content.strip()):
        raise HTTPException(status_code=400, detail="Provide file or text_content")

    upload_root = Path(settings.upload_root)
    now = datetime.utcnow()

    if file is not None:
        payload = await file.read()
        mime_type = file.content_type or "application/octet-stream"
        file_path = store_binary_file(upload_root, "positions", position_id, file.filename or "upload.bin", payload)
        extracted = extract_text_from_payload(payload, mime_type, file.filename or "upload.bin")
        file_name = file.filename or file_path.name
    else:
        inline = (text_content or "").strip()
        file_path = store_text_file(upload_root, "positions", position_id, inline)
        mime_type = "text/plain"
        extracted = inline
        file_name = file_path.name

    row = PositionDocument(
        document_id=str(uuid4()),
        position_id=position_id,
        document_type=document_type,
        file_name=file_name,
        file_path=str(file_path),
        mime_type=mime_type,
        extracted_text=extracted,
        is_processed=bool(extracted.strip()),
        created_at=now,
        updated_at=now,
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    refresh_position_evals_staleness(db, position_id)

    return DocumentUploadResponse(
        document_id=row.document_id,
        file_name=row.file_name,
        mime_type=row.mime_type,
        is_processed=bool(row.is_processed),
        extracted_chars=len(row.extracted_text or ""),
    )


@router.get("/{position_id}/dashboard", response_model=PositionDashboardResponse)
def get_position_dashboard(
    position_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PositionDashboardResponse:
    position = (
        db.query(Position)
        .filter(Position.position_id == position_id)
        .first()
    )
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    if current_user.role != "admin" and position.owner_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Position not found")

    rows = (
        db.query(Candidate, Evaluation)
        .outerjoin(Evaluation, and_(Evaluation.candidate_id == Candidate.candidate_id))
        .filter(Candidate.position_id == position_id)
        .order_by(Evaluation.overall_score.desc())
        .all()
    )

    stats = DashboardStats(total=len(rows), recommended=0, consider=0, not_recommended=0, pending=0)
    items: list[CandidateDashboardItem] = []

    for candidate, evaluation in rows:
        rec = (evaluation.recommendation or "").upper() if evaluation else ""
        if rec == "DOPORUCIT":
            stats.recommended += 1
        elif rec == "ZVAZIT":
            stats.consider += 1
        elif rec == "NEDOPORUCIT":
            stats.not_recommended += 1
        else:
            stats.pending += 1

        card: dict | None = None
        if evaluation and evaluation.evaluation_json:
            try:
                card = json.loads(evaluation.evaluation_json)
            except (json.JSONDecodeError, TypeError):
                card = None

        items.append(
            CandidateDashboardItem(
                candidate_id=candidate.candidate_id,
                full_name=candidate.full_name,
                email=candidate.email,
                external_ref=candidate.external_ref or "",
                evaluation_status=evaluation.status if evaluation else None,
                recommendation=evaluation.recommendation if evaluation else None,
                overall_score=float(evaluation.overall_score) if evaluation and evaluation.overall_score is not None else None,
                must_have_score=float(evaluation.must_have_score) if evaluation and evaluation.must_have_score is not None else None,
                card=card,
                is_stale=bool(evaluation.is_stale) if evaluation else False,
                stale_reason=evaluation.stale_reason if evaluation else None,
            )
        )

    return PositionDashboardResponse(
        position_id=position.position_id,
        title=position.title,
        description=position.description,
        status=position.status,
        opened_at=position.opened_at,
        stats=stats,
        candidates=items,
    )

