"""Staleness tracking for evaluations via document hash comparison."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _sha256_short(texts: list[str]) -> str:
    combined = "\n\n---\n\n".join(texts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:32]


def compute_candidate_docs_hash(db: "Session", candidate_id: str) -> str | None:
    from app.models import CandidateDocument

    docs = (
        db.query(CandidateDocument)
        .filter(CandidateDocument.candidate_id == candidate_id)
        .order_by(CandidateDocument.created_at)
        .all()
    )
    texts = [d.extracted_text for d in docs if d.extracted_text]
    return _sha256_short(texts) if texts else None


def compute_position_docs_hash(db: "Session", position_id: str) -> str | None:
    from app.models import PositionDocument

    docs = (
        db.query(PositionDocument)
        .filter(PositionDocument.position_id == position_id)
        .order_by(PositionDocument.created_at)
        .all()
    )
    texts = [d.extracted_text for d in docs if d.extracted_text]
    return _sha256_short(texts) if texts else None


def refresh_candidate_eval_staleness(db: "Session", candidate_id: str) -> None:
    """Recompute candidate docs hash and update is_stale on the evaluation record.

    - If current hash != stored hash at eval time → mark stale.
    - If hashes match again (e.g. same file re-uploaded) → clear stale if it was due to candidate docs.
    """
    from app.models import Evaluation

    row = (
        db.query(Evaluation)
        .filter(Evaluation.candidate_id == candidate_id, Evaluation.status == "completed")
        .first()
    )
    if row is None or row.candidate_docs_hash is None:
        return

    current = compute_candidate_docs_hash(db, candidate_id)
    if current != row.candidate_docs_hash:
        row.is_stale = True
        row.stale_reason = "candidate_docs_changed"
    elif row.stale_reason == "candidate_docs_changed":
        # Docs restored to exactly what they were at evaluation time
        row.is_stale = False
        row.stale_reason = None
    row.updated_at = datetime.utcnow()
    db.commit()


def refresh_position_evals_staleness(db: "Session", position_id: str) -> None:
    """Recompute position docs hash, update is_stale on all candidate evaluations,
    and invalidate the position's criteria cache if docs changed."""
    from app.models import Candidate, Evaluation, Position

    current = compute_position_docs_hash(db, position_id)

    # Invalidate criteria cache if position docs hash changed
    position = db.query(Position).filter(Position.position_id == position_id).first()
    if position and position.criteria_hash != current:
        position.criteria_json = None
        position.criteria_hash = None

    rows = (
        db.query(Evaluation)
        .join(Candidate, Candidate.candidate_id == Evaluation.candidate_id)
        .filter(Candidate.position_id == position_id, Evaluation.status == "completed")
        .all()
    )
    now = datetime.utcnow()
    for row in rows:
        if row.position_docs_hash is None:
            continue
        if current != row.position_docs_hash:
            row.is_stale = True
            row.stale_reason = "position_docs_changed"
        elif row.stale_reason == "position_docs_changed":
            row.is_stale = False
            row.stale_reason = None
        row.updated_at = now
    db.commit()


def save_evaluation_hashes(db: "Session", row, candidate_id: str, position_id: str) -> None:
    """After successful evaluation: store current docs hashes and clear stale flag."""
    row.candidate_docs_hash = compute_candidate_docs_hash(db, candidate_id)
    row.position_docs_hash = compute_position_docs_hash(db, position_id)
    row.is_stale = False
    row.stale_reason = None
