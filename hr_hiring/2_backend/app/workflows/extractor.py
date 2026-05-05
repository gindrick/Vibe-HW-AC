"""
Profile extraction from candidate documents.
Hash-cached: LLM is called only when document content has changed since last extraction.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, UTC
from typing import Any

logger = logging.getLogger(__name__)

from litellm import completion
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Candidate, CandidateDocument

EXTRACTOR_PROMPT = """You are an expert CV/resume parser. Extract candidate information from the document and return a JSON object with exactly these fields:

{
  "full_name": "string — full name of the candidate (required, never null)",
  "email": "string or null",
  "phone": "string or null",
  "current_role": "string or null — current or most recent job title",
  "years_experience": null or integer — estimated total professional experience in years,
  "skills": ["array of strings — up to 10 key technical or professional skills"],
  "education": "string or null — highest degree and institution",
  "salary_expectation": "string or null — only if explicitly stated in the document",
  "notice_period": "string or null — availability or notice period if mentioned",
  "languages": ["array of strings — e.g. Czech (native), English B2"],
  "summary": "string — 2-3 sentences describing the candidate's background and strengths"
}

Return ONLY the JSON object. No markdown, no explanation, no extra text."""


def _compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _call_llm(text: str) -> dict[str, Any]:
    t0 = time.monotonic()
    resp = completion(
        model=settings.litellm_model,
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
        custom_llm_provider="openai",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": EXTRACTOR_PROMPT},
            {"role": "user", "content": f"Extract candidate profile from this document:\n\n{text[:8000]}"},
        ],
    )
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    usage = getattr(resp, "usage", None)
    tok_in  = getattr(usage, "prompt_tokens", "?")
    tok_out = getattr(usage, "completion_tokens", "?")
    tok_tot = getattr(usage, "total_tokens", "?")
    logger.info(
        "[LLM] %-20s | model=%-20s | %5d ms | in=%-5s out=%-5s total=%s tokens",
        "extractor", settings.litellm_model, elapsed_ms, tok_in, tok_out, tok_tot,
    )
    raw = resp.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def extract_and_save_profile(db: Session, candidate_id: str) -> dict[str, Any]:
    """
    Extract a structured CandidateProfile from the candidate's documents.

    Hash-caching: computes SHA256 of combined document text. If the hash matches
    the value stored inside profile_json._hash, returns the cached profile without
    calling the LLM.

    Side-effects:
      - Updates candidate.profile_json and candidate.profile_status = "done"
      - Updates candidate.full_name if it is a placeholder (starts with "_")
      - Updates candidate.email if currently empty

    Returns the profile dict (without the internal _hash key).
    """
    candidate = db.query(Candidate).filter(Candidate.candidate_id == candidate_id).first()
    if candidate is None:
        raise ValueError(f"Candidate not found: {candidate_id}")

    docs = (
        db.query(CandidateDocument)
        .filter(CandidateDocument.candidate_id == candidate_id)
        .order_by(CandidateDocument.created_at)
        .all()
    )
    if not docs:
        raise ValueError(f"No documents for candidate: {candidate_id}")

    # Prioritise CV docs; append others for context
    cv_docs = [d for d in docs if d.document_type == "cv"]
    other_docs = [d for d in docs if d.document_type != "cv"]
    combined_text = "\n\n---\n\n".join(
        d.extracted_text for d in (cv_docs + other_docs) if d.extracted_text
    )
    if not combined_text.strip():
        raise ValueError(f"No extractable text for candidate: {candidate_id}")

    new_hash = _compute_hash(combined_text)

    # Check cached hash stored inside profile_json
    cached: dict[str, Any] = {}
    if candidate.profile_json:
        try:
            cached = json.loads(candidate.profile_json)
        except Exception:
            cached = {}

    if cached.get("_hash") == new_hash:
        logger.info("[LLM] %-20s | CACHE HIT — skipped (candidate %s)", "extractor", candidate_id)
        return {k: v for k, v in cached.items() if not k.startswith("_")}

    # Call LLM
    profile = _call_llm(combined_text)
    profile["_hash"] = new_hash

    # Persist
    now = datetime.now(UTC)
    candidate.profile_json = json.dumps(profile, ensure_ascii=False)
    candidate.profile_status = "done"

    # Fill in any empty fields from extracted profile
    if candidate.full_name.startswith("_") and profile.get("full_name"):
        candidate.full_name = str(profile["full_name"])[:250]
    if not candidate.email and profile.get("email"):
        candidate.email = str(profile["email"])[:320]
    if not candidate.phone and profile.get("phone"):
        candidate.phone = str(profile["phone"])[:64]

    candidate.updated_at = now
    db.commit()

    return {k: v for k, v in profile.items() if not k.startswith("_")}
