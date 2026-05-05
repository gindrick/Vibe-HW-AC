"""
Reset a position and its candidates for a clean cost-measurement run.

Usage (from 2_backend/ dir):
    python -m scripts.reset_cost_test --position-id <UUID>
    python -m scripts.reset_cost_test --position-title "Partial title"

What it clears:
  - Position.criteria_hash / criteria_json  → forces fresh jd_analyzer LLM call
  - Evaluations for all candidates on that position  → deleted entirely
  - Candidates.profile_json / profile_status  → back to pending
"""
from __future__ import annotations

import argparse
import sys

from app.database import SessionLocal
from app.models import Candidate, Evaluation, Position


def reset_position(position_id: str | None, title_fragment: str | None) -> None:
    db = SessionLocal()
    try:
        if position_id:
            pos = db.query(Position).filter(Position.position_id == position_id).first()
        else:
            pos = (
                db.query(Position)
                .filter(Position.title.ilike(f"%{title_fragment}%"))
                .first()
            )

        if pos is None:
            print("ERROR: position not found", file=sys.stderr)
            sys.exit(1)

        print(f"Position: {pos.position_id}  title={pos.title!r}")

        # 1) Clear criteria cache → next run calls jd_analyzer LLM
        pos.criteria_hash = None
        pos.criteria_json = None
        print("  cleared criteria_hash / criteria_json")

        # 2) Delete evaluations for all candidates on this position
        candidates = db.query(Candidate).filter(Candidate.position_id == pos.position_id).all()
        print(f"  candidates: {len(candidates)}")
        for c in candidates:
            deleted = (
                db.query(Evaluation)
                .filter(Evaluation.candidate_id == c.candidate_id)
                .delete(synchronize_session=False)
            )
            print(f"    {c.candidate_id} ({c.full_name!r})  — deleted {deleted} evaluation(s)")

            # 3) Reset extracted profile so it's treated as fresh
            c.profile_json = None
            c.profile_status = "pending"

        db.commit()
        print("Done — run is ready for fresh cost measurement.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--position-id", help="Exact position UUID")
    group.add_argument("--position-title", help="Substring of position title (case-insensitive)")
    args = parser.parse_args()
    reset_position(args.position_id, args.position_title)
