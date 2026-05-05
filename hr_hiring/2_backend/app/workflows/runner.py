from __future__ import annotations

import json
import logging
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, cast

import litellm

logger = logging.getLogger(__name__)
_costs_log = logging.getLogger("costs")

from langgraph.graph import END, StateGraph
from litellm import completion
from sqlalchemy.orm import Session

from app.config import ROOT, settings
from app.models import Candidate, Evaluation, Position
from app.workflows.hashing import compute_position_docs_hash
from app.workflows.prompts import EVALUATOR_PROMPT, JD_ANALYZER_PROMPT
from app.workflows.schemas import CandidateEvaluationCard, CriterionEvaluation, SkillTag
from app.workflows.state import EvalState
from app.workflows.tool_gateway import gateway


_LLM_LOGS_DIR = ROOT / "logs" / "llm_calls"


def _write_llm_log(
    caller: str,
    system_prompt: str,
    user_prompt: str,
    raw_response: str,
    usage: dict,
    cost_usd: str,
    elapsed_ms: int,
    candidate_id: str | None = None,
) -> None:
    _LLM_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    filename = f"{now.strftime('%d%m%y')}_{caller}.json"
    log_entry = {
        "timestamp": now.isoformat(),
        "caller": caller,
        "candidate_id": candidate_id,
        "elapsed_ms": elapsed_ms,
        "usage": usage,
        "cost_usd": cost_usd,
        "request": {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        "response": {
            "content": raw_response,
        },
    }
    log_path = _LLM_LOGS_DIR / filename
    # append as JSON-lines so multiple calls on the same day don't overwrite
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


def _llm_json(system_prompt: str, user_prompt: str, caller: str = "unknown", candidate_id: str | None = None) -> dict[str, Any]:
    t0 = time.monotonic()
    response = completion(
        model=settings.litellm_model,
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
        custom_llm_provider="openai",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    usage = getattr(response, "usage", None)
    tok_in  = getattr(usage, "prompt_tokens", "?")
    tok_out = getattr(usage, "completion_tokens", "?")
    tok_tot = getattr(usage, "total_tokens", "?")
    logger.info(
        "[LLM] %-20s | model=%-20s | %5d ms | in=%-5s out=%-5s total=%s tokens",
        caller, settings.litellm_model, elapsed_ms, tok_in, tok_out, tok_tot,
    )

    # --- costs.log entry ---
    content = response.choices[0].message.content or "{}"
    try:
        total_cost = litellm.completion_cost(completion_response=response)
    except Exception:
        total_cost = None
    cost_str = f"{total_cost:.8f}" if total_cost else "N/A"
    prompt_snip  = user_prompt[:100].replace("\n", " ")
    response_snip = content[:100].replace("\n", " ")
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    _costs_log.info(
        "%s | caller=%-12s | in=%-5s out=%-5s total=%-6s | cost_usd=%s"
        " | prompt=%.100r | response=%.100r",
        ts, caller, tok_in, tok_out, tok_tot, cost_str, prompt_snip, response_snip,
    )
    # --- end costs.log ---

    # --- llm call log ---
    _write_llm_log(
        caller=caller,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        raw_response=content,
        usage={"prompt_tokens": tok_in, "completion_tokens": tok_out, "total_tokens": tok_tot},
        cost_usd=cost_str,
        elapsed_ms=elapsed_ms,
        candidate_id=candidate_id,
    )
    # --- end llm call log ---

    parsed = json.loads(content)
    return parsed if isinstance(parsed, dict) else {}


def _recommendation(must_have_score: float) -> str:
    if must_have_score >= 3.5:
        return "DOPORUCIT"
    if must_have_score >= 2.5:
        return "ZVAZIT"
    return "NEDOPORUCIT"


def _extract_interview_text(candidate_context: str) -> str:
    chunks = []
    for part in candidate_context.split("\n\n---\n\n"):
        if part.lower().startswith("[interview_transcript]"):
            chunks.append(part)
    return "\n\n".join(chunks)


def _fallback_criteria(jd_text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for line in jd_text.splitlines():
        raw = line.strip(" -\t")
        if len(raw) < 8:
            continue
        lowered = raw.lower()
        if any(k in lowered for k in ["must", "required", "essential"]):
            items.append({"name": raw, "criterion_type": "must_have"})
        elif any(k in lowered for k in ["nice", "plus", "preferred", "bonus"]):
            items.append({"name": raw, "criterion_type": "nice_to_have"})
    if not items:
        items = [{"name": "Relevant professional experience", "criterion_type": "must_have"}]
    return items[:20]


def _fallback_card(state: EvalState, criteria: list[dict[str, Any]]) -> CandidateEvaluationCard:
    eval_criteria: list[CriterionEvaluation] = []
    for c in criteria:
        eval_criteria.append(
            CriterionEvaluation(
                name=str(c.get("name", "Unnamed criterion")),
                criterion_type=(
                    "must_have" if c.get("criterion_type") == "must_have" else "nice_to_have"
                ),
                score=3,
                evidence="Insufficient structured evidence from documents in fallback mode.",
            )
        )

    must_scores = [c.score for c in eval_criteria if c.criterion_type == "must_have"]
    nice_scores = [c.score for c in eval_criteria if c.criterion_type == "nice_to_have"]
    must_avg = sum(must_scores) / max(len(must_scores), 1)
    nice_avg = sum(nice_scores) / max(len(nice_scores), 1)
    overall = round((must_avg * 0.7 + nice_avg * 0.3), 2) if nice_scores else round(must_avg, 2)

    return CandidateEvaluationCard(
        candidate_id=state["candidate_id"],
        position_id=state["position_id"],
        criteria=eval_criteria,
        must_have_score=round(must_avg, 2),
        overall_score=overall,
        recommendation=_recommendation(must_avg),
        recommendation_rationale="Automatic fallback evaluation. Manual review is recommended.",
        strengths=["Candidate profile available."],
        gaps=["LLM structured response unavailable in this run."],
        red_flags=[],
        interview_questions=["Can you describe your most relevant recent project?"],
        model_used="fallback",
        evaluated_at=datetime.now(UTC),
        schema_version="1.0.0",
    )


def _build_graph():
    graph = StateGraph(EvalState)

    def load_documents(state: EvalState) -> EvalState:
        jd_context = gateway.build_jd_context(state["position_id"])
        candidate_context = gateway.build_candidate_context(state["candidate_id"])
        return {
            **state,
            "jd_text": jd_context,
            "cv_text": candidate_context,
            "interview_text": _extract_interview_text(candidate_context),
        }

    def jd_analyzer(state: EvalState) -> EvalState:
        if state.get("criteria_from_cache"):
            logger.info("[LLM] %-20s | CACHE HIT — skipped (position %s)", "jd_analyzer", state["position_id"])
            return state

        criteria = _fallback_criteria(state["jd_text"])
        try:
            llm_out = _llm_json(
                JD_ANALYZER_PROMPT,
                f"JD text:\n{state['jd_text']}\n\nReturn criteria JSON array.",
                caller="jd_analyzer",
                candidate_id=state.get("candidate_id"),
            )
            if isinstance(llm_out.get("criteria"), list):
                criteria = cast(list[dict[str, Any]], llm_out["criteria"])
        except Exception as e:
            logger.error("jd_analyzer LLM error: %s", e, exc_info=True)

        return {**state, "criteria_json": json.dumps(criteria, ensure_ascii=True)}

    def evaluator(state: EvalState) -> EvalState:
        criteria = cast(list[dict[str, Any]], json.loads(state["criteria_json"] or "[]"))

        try:
            llm_out = _llm_json(
                EVALUATOR_PROMPT,
                (
                    f"Position title: {state['position_title']}\n"
                    f"Criteria: {json.dumps(criteria, ensure_ascii=True)}\n"
                    f"Candidate docs:\n{state['cv_text']}\n\n"
                    "Return JSON object only."
                ),
                caller="evaluator",
                candidate_id=state.get("candidate_id"),
            )

            criteria_items = []
            for item in llm_out.get("criteria", []):
                criteria_items.append(
                    CriterionEvaluation(
                        name=str(item.get("name", "Unnamed criterion")),
                        criterion_type=(
                            "must_have"
                            if str(item.get("criterion_type", "must_have")) == "must_have"
                            else "nice_to_have"
                        ),
                        score=int(item.get("score", 3)),
                        evidence=str(item.get("evidence", "No evidence provided.")),
                    )
                )

            if not criteria_items:
                card = _fallback_card(state, criteria)
                return {**state, "evaluation_card": card.model_dump(mode="json"), "extracted_profile": llm_out.get("candidate_profile") or {}}

            must_scores = [c.score for c in criteria_items if c.criterion_type == "must_have"]
            nice_scores = [c.score for c in criteria_items if c.criterion_type == "nice_to_have"]
            must_avg = sum(must_scores) / max(len(must_scores), 1)
            nice_avg = sum(nice_scores) / max(len(nice_scores), 1)
            overall = round((must_avg * 0.7 + nice_avg * 0.3), 2) if nice_scores else round(must_avg, 2)

            # Parse skill_tags
            raw_tags = llm_out.get("skill_tags") or []
            skill_tags = []
            for t in raw_tags[:10]:
                if isinstance(t, dict):
                    status = str(t.get("status", "neutral"))
                    if status not in ("match", "gap", "neutral"):
                        status = "neutral"
                    skill_tags.append(SkillTag(label=str(t.get("label", ""))[:20], status=status))  # type: ignore[arg-type]

            card = CandidateEvaluationCard(
                candidate_id=state["candidate_id"],
                position_id=state["position_id"],
                criteria=criteria_items,
                must_have_score=round(must_avg, 2),
                overall_score=overall,
                recommendation=_recommendation(must_avg),
                recommendation_rationale=str(
                    llm_out.get("recommendation_rationale", "Evaluation based on submitted documents.")
                ),
                strengths=[str(x) for x in llm_out.get("strengths", [])][:5],
                gaps=[str(x) for x in llm_out.get("gaps", [])][:5],
                red_flags=[str(x) for x in llm_out.get("red_flags", [])][:5],
                interview_questions=[str(x) for x in llm_out.get("interview_questions", [])][:5],
                current_role=str(llm_out["current_role"]) if llm_out.get("current_role") else None,
                salary_expectation=str(llm_out["salary_expectation"]) if llm_out.get("salary_expectation") else None,
                availability=str(llm_out["availability"]) if llm_out.get("availability") else None,
                skill_tags=skill_tags,
                model_used=settings.litellm_model,
                evaluated_at=datetime.now(UTC),
                schema_version="1.1.0",
            )
            extracted_profile = llm_out.get("candidate_profile") or {}
            return {**state, "evaluation_card": card.model_dump(mode="json"), "extracted_profile": extracted_profile}
        except Exception as e:
            logger.error("evaluator LLM error: %s", e, exc_info=True)
            card = _fallback_card(state, criteria)
            return {**state, "evaluation_card": card.model_dump(mode="json"), "extracted_profile": {}}

    def output_formatter(state: EvalState) -> EvalState:
        card = CandidateEvaluationCard.model_validate(state["evaluation_card"])
        gateway.save_evaluation(
            candidate_id=state["candidate_id"],
            card_json=card.model_dump_json(),
        )
        return {**state, "evaluation_card": card.model_dump(mode="json")}

    graph.add_node("load_documents", load_documents)
    graph.add_node("jd_analyzer", jd_analyzer)
    graph.add_node("evaluator", evaluator)
    graph.add_node("output_formatter", output_formatter)

    graph.set_entry_point("load_documents")
    graph.add_edge("load_documents", "jd_analyzer")
    graph.add_edge("jd_analyzer", "evaluator")
    graph.add_edge("evaluator", "output_formatter")
    graph.add_edge("output_formatter", END)

    return graph.compile()


compiled_graph = _build_graph()


def run_candidate_evaluation(db: Session, candidate_id: str) -> dict[str, Any]:
    candidate = db.query(Candidate).filter(Candidate.candidate_id == candidate_id).first()
    if candidate is None:
        raise ValueError(f"Candidate not found: {candidate_id}")

    position = db.query(Position).filter(Position.position_id == candidate.position_id).first()
    if position is None:
        raise ValueError(f"Position not found for candidate: {candidate_id}")

    # Check criteria cache: if position docs hash matches stored hash, skip jd_analyzer LLM call
    current_pos_hash = compute_position_docs_hash(db, position.position_id)
    cache_hit = (
        current_pos_hash is not None
        and position.criteria_hash == current_pos_hash
        and position.criteria_json
    )

    initial_state: EvalState = {
        "position_id": candidate.position_id,
        "candidate_id": candidate_id,
        "position_title": position.title,
        "jd_text": "",
        "cv_text": "",
        "interview_text": "",
        "criteria_json": position.criteria_json if cache_hit else "[]",
        "criteria_from_cache": bool(cache_hit),
        "evaluation_card": {},
        "extracted_profile": {},
        "error": None,
    }

    final_state = cast(EvalState, compiled_graph.invoke(initial_state))

    # If criteria came fresh from LLM, save them back to the position for future candidates
    if not cache_hit and final_state.get("criteria_json", "[]") != "[]":
        position.criteria_json = final_state["criteria_json"]
        position.criteria_hash = current_pos_hash
        db.commit()
        logger.info("Saved criteria cache for position %s", position.position_id)

    # Save candidate profile extracted by the evaluator (replaces separate extractor LLM call)
    if final_state.get("extracted_profile"):
        _save_extracted_profile(db, candidate_id, final_state["extracted_profile"])

    return final_state["evaluation_card"]


def _save_extracted_profile(db: Session, candidate_id: str, profile_data: dict) -> None:
    """Save candidate_profile extracted by the evaluator LLM into the Candidate record."""
    candidate = db.query(Candidate).filter(Candidate.candidate_id == candidate_id).first()
    if candidate is None:
        return
    candidate.profile_json = json.dumps(profile_data, ensure_ascii=False)
    candidate.profile_status = "done"
    if candidate.full_name.startswith("_") and profile_data.get("full_name"):
        candidate.full_name = str(profile_data["full_name"])[:250]
    if not candidate.email and profile_data.get("email"):
        candidate.email = str(profile_data["email"])[:320]
    if not candidate.phone and profile_data.get("phone"):
        candidate.phone = str(profile_data["phone"])[:64]
    candidate.updated_at = datetime.now(UTC)
    db.commit()


def mark_evaluation_failed(db: Session, candidate_id: str, error_message: str) -> None:
    record = db.query(Evaluation).filter(Evaluation.candidate_id == candidate_id).first()
    if record is None:
        return
    record.status = "failed"
    record.error_message = error_message[:4000]
    record.updated_by = "workflow"
    db.commit()
