from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from app.database import Base, SessionLocal, engine
from app.models import Candidate, Evaluation, Position, User


def _ensure_user(db: SessionLocal, email: str, display_name: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user

    now = datetime.utcnow()
    user = User(
        user_id=str(uuid4()),
        entra_object_id=f"seed-{uuid4()}",
        email=email,
        display_name=display_name,
        role="hm",
        is_active=True,
        created_at=now,
        updated_at=now,
        created_by="seed",
        updated_by="seed",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _ensure_position(db: SessionLocal, owner_id: str) -> Position:
    position = db.query(Position).filter(Position.owner_id == owner_id, Position.title == "Senior Data Engineer").first()
    if position:
        return position

    now = datetime.utcnow()
    position = Position(
        position_id=str(uuid4()),
        owner_id=owner_id,
        title="Senior Data Engineer",
        description="Build and maintain analytics platform and data pipelines.",
        status="active",
        created_at=now,
        updated_at=now,
        created_by="seed",
        updated_by="seed",
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


def _ensure_candidate(db: SessionLocal, position_id: str, full_name: str, email: str, external_ref: str) -> Candidate:
    row = db.query(Candidate).filter(Candidate.position_id == position_id, Candidate.full_name == full_name).first()
    if row:
        return row

    now = datetime.utcnow()
    row = Candidate(
        candidate_id=str(uuid4()),
        position_id=position_id,
        full_name=full_name,
        email=email,
        phone="",
        external_ref=external_ref,
        notes="Seed demo candidate",
        created_at=now,
        updated_at=now,
        created_by="seed",
        updated_by="seed",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ensure_evaluation(db: SessionLocal, candidate: Candidate, position: Position) -> Evaluation:
    row = db.query(Evaluation).filter(Evaluation.candidate_id == candidate.candidate_id).first()
    if row:
        return row

    card = {
        "candidate_id": candidate.candidate_id,
        "position_id": position.position_id,
        "criteria": [
            {
                "name": "Python data engineering",
                "criterion_type": "must_have",
                "score": 4,
                "evidence": "Led ETL migration to modern pipeline stack.",
            },
            {
                "name": "Cloud platform",
                "criterion_type": "must_have",
                "score": 3,
                "evidence": "Hands-on Azure usage on analytics workloads.",
            },
            {
                "name": "Stakeholder communication",
                "criterion_type": "nice_to_have",
                "score": 4,
                "evidence": "Regularly presented KPI reports to business owners.",
            },
        ],
        "must_have_score": 3.5,
        "overall_score": 3.65,
        "recommendation": "DOPORUCIT",
        "recommendation_rationale": "Solid technical match with clear evidence in the profile.",
        "strengths": ["Pipeline ownership", "Good Python practices", "Business communication"],
        "gaps": ["Needs deeper platform architecture depth"],
        "red_flags": [],
        "interview_questions": [
            "How do you design incremental ETL for late-arriving data?",
            "How do you monitor data quality and SLA breaches?",
            "What trade-offs do you make when modeling warehouse schemas?",
        ],
        "model_used": "seed",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "schema_version": "1.0.0",
    }

    now = datetime.utcnow()
    row = Evaluation(
        evaluation_id=str(uuid4()),
        candidate_id=candidate.candidate_id,
        position_id=position.position_id,
        status="completed",
        recommendation="DOPORUCIT",
        overall_score=3.65,
        must_have_score=3.5,
        evaluation_json=json.dumps(card, ensure_ascii=True),
        error_message="",
        model_used="seed",
        schema_version="1.0.0",
        created_at=now,
        updated_at=now,
        created_by="seed",
        updated_by="seed",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = _ensure_user(db, email="hm@example.com", display_name="Demo Hiring Manager")
        position = _ensure_position(db, owner_id=user.user_id)

        candidate_a = _ensure_candidate(
            db,
            position_id=position.position_id,
            full_name="Alice Novak",
            email="alice.novak@example.com",
            external_ref="ATS-1001",
        )
        candidate_b = _ensure_candidate(
            db,
            position_id=position.position_id,
            full_name="Martin Svoboda",
            email="martin.svoboda@example.com",
            external_ref="ATS-1002",
        )

        evaluation = _ensure_evaluation(db, candidate=candidate_a, position=position)

        print("Seed complete")
        print(f"User: {user.email} ({user.user_id})")
        print(f"Position: {position.title} ({position.position_id})")
        print(f"Candidate 1: {candidate_a.full_name} ({candidate_a.candidate_id})")
        print(f"Candidate 2: {candidate_b.full_name} ({candidate_b.candidate_id})")
        print(f"Evaluation: {evaluation.evaluation_id} status={evaluation.status}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
