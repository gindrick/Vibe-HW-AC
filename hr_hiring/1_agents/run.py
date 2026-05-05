"""
HR Hiring Agent CLI

Usage:
  # Evaluate one candidate:
  python run.py candidate --id <candidate_id>

  # Evaluate all pending candidates for a position:
  python run.py position --id <position_id>

  # List candidates for a position:
  python run.py list --position-id <position_id>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure local modules resolve correctly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import get_session
from agents.evaluator import batch_evaluate_position, evaluate_candidate


def cmd_candidate(args: argparse.Namespace) -> None:
    db = get_session()
    try:
        print(f"Evaluating candidate {args.id} …")
        card = evaluate_candidate(db, args.id)
        print(json.dumps(card, indent=2, ensure_ascii=False, default=str))
    finally:
        db.close()


def cmd_position(args: argparse.Namespace) -> None:
    db = get_session()
    try:
        print(f"Batch evaluating all pending candidates for position {args.id} …")
        results = batch_evaluate_position(db, args.id)
        print(f"\nDone: {len(results)} candidates processed.")
        recommended = sum(1 for r in results if r.get("recommendation") == "DOPORUCIT")
        consider = sum(1 for r in results if r.get("recommendation") == "ZVAZIT")
        failed = sum(1 for r in results if r.get("status") == "failed")
        print(f"  DOPORUCIT: {recommended}  ZVAZIT: {consider}  Chyba: {failed}")
    finally:
        db.close()


def cmd_list(args: argparse.Namespace) -> None:
    from sqlalchemy import text
    db = get_session()
    try:
        rows = db.execute(
            text(
                """
                SELECT c.CandidateId, c.FullName, c.Email,
                       e.Status, e.Recommendation, e.OverallScore
                FROM hr_eval.Candidates c
                LEFT JOIN hr_eval.Evaluations e ON e.CandidateId = c.CandidateId
                WHERE c.PositionId = :pid
                ORDER BY c.CreatedAt ASC
                """
            ),
            {"pid": args.position_id},
        ).fetchall()
        print(f"{'ID':<38} {'Jméno':<30} {'Status':<12} {'Doporučení':<14} Score")
        print("-" * 100)
        for row in rows:
            print(
                f"{row.CandidateId:<38} {(row.FullName or ''):<30} "
                f"{(row.Status or 'nezahájeno'):<12} {(row.Recommendation or '—'):<14} "
                f"{row.OverallScore or '—'}"
            )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="HR Hiring Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_candidate = sub.add_parser("candidate", help="Evaluate one candidate")
    p_candidate.add_argument("--id", required=True, help="Candidate UUID")

    p_position = sub.add_parser("position", help="Batch evaluate all pending candidates")
    p_position.add_argument("--id", required=True, help="Position UUID")

    p_list = sub.add_parser("list", help="List candidates for a position")
    p_list.add_argument("--position-id", required=True, help="Position UUID")

    args = parser.parse_args()

    if args.command == "candidate":
        cmd_candidate(args)
    elif args.command == "position":
        cmd_position(args)
    elif args.command == "list":
        cmd_list(args)


if __name__ == "__main__":
    main()
