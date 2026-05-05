"""Smaže kandidáty s profile_status='failed' včetně jejich dokumentů a evaluací."""
from app.database import SessionLocal
from app.models import Candidate, CandidateDocument, Evaluation

db = SessionLocal()
try:
    failed = db.query(Candidate).filter(Candidate.profile_status == "failed").all()
    print(f"Nalezeno {len(failed)} failed kandidátů:")
    for c in failed:
        print(f"  {c.candidate_id} — {c.full_name}")
        db.query(CandidateDocument).filter(CandidateDocument.candidate_id == c.candidate_id).delete()
        db.query(Evaluation).filter(Evaluation.candidate_id == c.candidate_id).delete()
        db.delete(c)
    db.commit()
    print("Smazáno.")
finally:
    db.close()
