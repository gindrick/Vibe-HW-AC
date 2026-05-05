from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from app.config import ROOT

router = APIRouter(prefix="/llm", tags=["llm"])

_LLM_LOGS_DIR = ROOT / "logs" / "llm_calls"


def _load_all_entries() -> list[dict]:
    entries = []
    if not _LLM_LOGS_DIR.exists():
        return entries
    for log_file in sorted(_LLM_LOGS_DIR.glob("*.json")):
        for line in log_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
    return entries


@router.get("/stats")
def llm_stats(candidate_id: str | None = None) -> dict:
    """
    Aggregate token usage from LLM call logs.
    Optionally filter by candidate_id.
    Returns total tokens in/out, per-caller breakdown, and per-candidate breakdown.
    """
    entries = _load_all_entries()
    if candidate_id:
        entries = [e for e in entries if e.get("candidate_id") == candidate_id]

    total_in = 0
    total_out = 0
    total_calls = 0
    by_caller: dict[str, dict] = {}
    by_candidate: dict[str, dict] = {}

    for e in entries:
        usage = e.get("usage", {})
        tok_in = usage.get("prompt_tokens") or 0
        tok_out = usage.get("completion_tokens") or 0
        if not isinstance(tok_in, int):
            tok_in = 0
        if not isinstance(tok_out, int):
            tok_out = 0

        total_in += tok_in
        total_out += tok_out
        total_calls += 1

        caller = e.get("caller", "unknown")
        if caller not in by_caller:
            by_caller[caller] = {"calls": 0, "tokens_in": 0, "tokens_out": 0}
        by_caller[caller]["calls"] += 1
        by_caller[caller]["tokens_in"] += tok_in
        by_caller[caller]["tokens_out"] += tok_out

        cid = e.get("candidate_id")
        if cid:
            if cid not in by_candidate:
                by_candidate[cid] = {"calls": 0, "tokens_in": 0, "tokens_out": 0}
            by_candidate[cid]["calls"] += 1
            by_candidate[cid]["tokens_in"] += tok_in
            by_candidate[cid]["tokens_out"] += tok_out

    return {
        "total_calls": total_calls,
        "total_tokens_in": total_in,
        "total_tokens_out": total_out,
        "total_tokens": total_in + total_out,
        "by_caller": by_caller,
        "by_candidate": by_candidate,
    }


@router.get("/stats/candidate/{candidate_id}")
def llm_stats_candidate(candidate_id: str) -> dict:
    """Token usage for a specific candidate."""
    return llm_stats(candidate_id=candidate_id)
