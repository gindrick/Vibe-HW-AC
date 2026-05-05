"""
Standalone evaluator agent.

Adds the backend to sys.path and runs the existing LangGraph evaluation workflow
directly against the MSSQL database using SQLAlchemy — no HTTP API needed.

Usage:
    from agents.evaluator import evaluate_candidate, batch_evaluate_position
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make backend importable
_BACKEND = Path(__file__).resolve().parents[2] / "2_backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.workflows.runner import mark_evaluation_failed, run_candidate_evaluation  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy import text  # noqa: E402


def evaluate_candidate(db: Session, candidate_id: str) -> dict:
    """
    Run full evaluation pipeline for one candidate.
    Returns the evaluation card dict.
    Saves result to DB automatically (via output_formatter node in the graph).
    """
    try:
        _ensure_evaluation_record(db, candidate_id)
        card = run_candidate_evaluation(db, candidate_id)
        return card
    except Exception as exc:
        mark_evaluation_failed(db, candidate_id, str(exc))
        raise


def batch_evaluate_position(db: Session, position_id: str) -> list[dict]:
    """
    Evaluate all candidates for a position that have no completed evaluation.
    Returns list of result dicts with candidate_id and status.
    """
    rows = db.execute(
        text(
            """
            SELECT c.CandidateId
            FROM hr_eval.Candidates c
            LEFT JOIN hr_eval.Evaluations e ON e.CandidateId = c.CandidateId
            WHERE c.PositionId = :position_id
              AND (e.Status IS NULL OR e.Status NOT IN ('completed'))
            ORDER BY c.CreatedAt ASC
            """
        ),
        {"position_id": position_id},
    ).fetchall()

    results = []
    for row in rows:
        candidate_id = row.CandidateId
        try:
            card = evaluate_candidate(db, candidate_id)
            results.append({
                "candidate_id": candidate_id,
                "status": "completed",
                "recommendation": card.get("recommendation"),
                "overall_score": card.get("overall_score"),
            })
            print(f"  ✓ {candidate_id} → {card.get('recommendation')} ({card.get('overall_score')})")
        except Exception as exc:
            results.append({"candidate_id": candidate_id, "status": "failed", "error": str(exc)})
            print(f"  ✗ {candidate_id} → {exc}")

    return results


def _ensure_evaluation_record(db: Session, candidate_id: str) -> None:
    """Create a pending evaluation record if one doesn't exist."""
    from uuid import uuid4
    from datetime import datetime

    existing = db.execute(
        text("SELECT TOP 1 EvaluationId FROM hr_eval.Evaluations WHERE CandidateId = :cid"),
        {"cid": candidate_id},
    ).first()

    if existing is None:
        pos_row = db.execute(
            text("SELECT TOP 1 PositionId FROM hr_eval.Candidates WHERE CandidateId = :cid"),
            {"cid": candidate_id},
        ).first()
        if pos_row is None:
            raise ValueError(f"Candidate not found: {candidate_id}")

        now = datetime.utcnow()
        db.execute(
            text(
                """
                INSERT INTO hr_eval.Evaluations
                    (EvaluationId, CandidateId, PositionId, Status,
                     CreatedAt, CreatedBy, UpdatedAt, UpdatedBy)
                VALUES
                    (:eid, :cid, :pid, 'pending',
                     :now, 'agent', :now, 'agent')
                """
            ),
            {"eid": str(uuid4()), "cid": candidate_id, "pid": pos_row.PositionId, "now": now},
        )
        db.commit()
    else:
        db.execute(
            text(
                "UPDATE hr_eval.Evaluations SET Status = 'pending', UpdatedAt = :now, UpdatedBy = 'agent' WHERE CandidateId = :cid"
            ),
            {"cid": candidate_id, "now": __import__("datetime").datetime.utcnow()},
        )
        db.commit()
