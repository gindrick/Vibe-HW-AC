from __future__ import annotations

from datetime import datetime, UTC
from typing import Literal

from pydantic import BaseModel, Field


class CriterionEvaluation(BaseModel):
    name: str
    criterion_type: Literal["must_have", "nice_to_have"]
    score: Literal[1, 2, 3, 4, 5]
    evidence: str


class SkillTag(BaseModel):
    label: str
    status: Literal["match", "gap", "neutral"] = "neutral"


class CandidateEvaluationCard(BaseModel):
    candidate_id: str
    position_id: str
    criteria: list[CriterionEvaluation]
    must_have_score: float = Field(ge=1.0, le=5.0)
    overall_score: float = Field(ge=1.0, le=5.0)
    recommendation: Literal["DOPORUCIT", "ZVAZIT", "NEDOPORUCIT"]
    recommendation_rationale: str
    strengths: list[str]
    gaps: list[str]
    red_flags: list[str]
    interview_questions: list[str]
    # enriched card fields
    current_role: str | None = None
    salary_expectation: str | None = None
    availability: str | None = None
    skill_tags: list[SkillTag] = Field(default_factory=list)
    model_used: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "1.1.0"
