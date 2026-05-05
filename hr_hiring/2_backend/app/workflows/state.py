from __future__ import annotations

from typing import TypedDict


class EvalState(TypedDict):
    position_id: str
    candidate_id: str
    position_title: str
    jd_text: str
    cv_text: str
    interview_text: str
    criteria_json: str
    criteria_from_cache: bool
    evaluation_card: dict
    extracted_profile: dict
    error: str | None
