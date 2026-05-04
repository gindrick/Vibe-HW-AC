"""
Multi-agent PDF extraction pipeline — LLM Supervisor pattern.

All LLM calls go through LiteLLM proxy (OpenAI-compatible API).
The model is selected via settings.agent_model, which maps to a model_name
in litellm_config.yaml (e.g. "anthropic-claude-sonnet-4", "llm-default").

The supervisor is an LLM agent that decides which sub-agents to call,
in what order, and how many revision cycles to run. It has five tools:
  - read_document      → runs the document-reader sub-agent
  - extract_form       → runs the form-extractor sub-agent (optionally with patches)
  - review_draft       → runs the validator-reviewer sub-agent
  - update_memory      → supervisor records observations and decisions (working memory)
  - finalize_result    → called by the supervisor when it is satisfied with quality

Sub-agents are single async calls to LiteLLM with JSON output.
Tool calls within one supervisor iteration execute in parallel via asyncio.gather().
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)
_costs_log = logging.getLogger("production_cards_2.costs")

# ── Pipeline limits ─────────────────────────────────────────────────────────

SUPERVISOR_MAX_ITERATIONS = 10  # max tool-call rounds for the LLM supervisor
SUBAGENT_TIMEOUT_SECONDS = 120  # wall-clock timeout per sub-agent call

# ── Card field names ─────────────────────────────────────────────────────────

CARD_FIELDS = [
    "title", "date", "line_number", "shift", "operator", "tool",
    "produced_dimension", "surface_treatment", "article_number",
    "material_granulate", "coating", "thickness", "width",
    "u_profile", "surface", "gloss", "notes",
    "footer_processed_by", "footer_approved_by",
]

# ── JSON Schema definitions ──────────────────────────────────────────────────

_STR_OR_NULL = {"anyOf": [{"type": "string"}, {"type": "null"}]}

DOCUMENT_READING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "header_text":          _STR_OR_NULL,
        "product_text":         _STR_OR_NULL,
        "measurements_text":    _STR_OR_NULL,
        "parameters_rows_raw":  {
            "type": "array",
            "items": {"type": "string"},
            "description": "Raw parameter table rows, each as one string",
        },
        "footer_text":          _STR_OR_NULL,
        "uncertain_regions":    {
            "type": "array",
            "items": {"type": "string"},
            "description": "Description of unreadable or unclear document regions",
        },
        "layout_notes":         _STR_OR_NULL,
    },
    "required": [
        "header_text", "product_text", "measurements_text",
        "parameters_rows_raw", "footer_text", "uncertain_regions", "layout_notes",
    ],
    "additionalProperties": False,
}

_PARAMETER_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "number": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "name":   {"type": "string"},
        "value":  {"type": "string"},
        "unit":   {"type": "string"},
    },
    "required": ["number", "name", "value", "unit"],
    "additionalProperties": False,
}

CARD_DATA_DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title":              _STR_OR_NULL,
        "date":               _STR_OR_NULL,
        "line_number":        _STR_OR_NULL,
        "shift":              _STR_OR_NULL,
        "operator":           _STR_OR_NULL,
        "tool":               _STR_OR_NULL,
        "produced_dimension": _STR_OR_NULL,
        "surface_treatment":  _STR_OR_NULL,
        "article_number":     _STR_OR_NULL,
        "material_granulate": _STR_OR_NULL,
        "coating":            _STR_OR_NULL,
        "thickness":          _STR_OR_NULL,
        "width":              _STR_OR_NULL,
        "u_profile":          _STR_OR_NULL,
        "surface":            _STR_OR_NULL,
        "gloss":              _STR_OR_NULL,
        "notes":              _STR_OR_NULL,
        "footer_processed_by": _STR_OR_NULL,
        "footer_approved_by":  _STR_OR_NULL,
        "parameters": {
            "type": "array",
            "items": _PARAMETER_ITEM_SCHEMA,
        },
        "uncertain_fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Field names where the agent was uncertain about the value",
        },
        "mapping_notes": _STR_OR_NULL,
    },
    "required": CARD_FIELDS + ["parameters", "uncertain_fields", "mapping_notes"],
    "additionalProperties": False,
}

_REVIEW_PATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "field":           {"type": "string"},
        "reason":          {"type": "string"},
        "suggested_value": _STR_OR_NULL,
    },
    "required": ["field", "reason", "suggested_value"],
    "additionalProperties": False,
}

REVIEW_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["approved", "needs_revision", "rejected"],
        },
        "field_patches": {
            "type": "array",
            "items": _REVIEW_PATCH_SCHEMA,
        },
        "missing_fields": {
            "type": "array",
            "items": {"type": "string"},
        },
        "suspicious_fields": {
            "type": "array",
            "items": {"type": "string"},
        },
        "review_notes": _STR_OR_NULL,
    },
    "required": ["decision", "field_patches", "missing_fields", "suspicious_fields"],
    "additionalProperties": False,
}

# ── System prompts ───────────────────────────────────────────────────────────

DOCUMENT_READER_SYSTEM = """You are an agent for reading industrial production cards from extrusion lines.
Your task is to read the document and describe its content — do NOT mechanically copy it into form fields.
Identify card sections: header (date, line, shift, operator), product (tool, dimension, material),
parameter table (rows with number, name, value, unit), notes, and footer.
Mark regions that are illegible, crossed out, or unclear.
Return a structured representation of the document — not final form fields.
Respond ONLY with valid JSON matching the given schema."""

FORM_EXTRACTOR_SYSTEM = """You are an agent for mapping production card content into a structured form.
You will receive a document description (DocumentReading) and your task is to fill in all CardData form fields precisely.
Rules:
- Copy values exactly as they appear in the document.
- If a field cannot be filled, return null.
- Temperatures, pressures, and speeds: separate the numeric value from the unit (value/unit).
- Sort parameters in ascending order by number.
- Fill uncertain_fields with names of fields you are not sure about.
- If you receive a list of corrections (field_patches), apply them — they take precedence over the original value.
Respond ONLY with valid JSON matching the given schema."""

VALIDATOR_REVIEWER_SYSTEM = """You are a QA agent for verifying extracted data from a production card.
You will receive the original document image, a document description (DocumentReading), and a proposed form draft (CardDataDraft).
Your task is to:
1. Compare the draft against the document — check whether values match.
2. Identify missing required fields (date, line, operator are critical).
3. Check parameter ordering, value/unit separation, and null values.
4. Decide:
   - approved: draft is sufficiently correct for saving
   - needs_revision: there are specific errors that can be corrected
   - rejected: document is illegible or draft is entirely unusable
Be specific in field_patches — provide exact corrections, not just comments.
Respond ONLY with valid JSON matching the given schema."""

SUPERVISOR_SYSTEM = """You are a supervisor coordinating extraction of structured data from scanned production card PDFs.

You have five tools: read_document, extract_form, review_draft, update_memory, finalize_result.

Your goal is accurate, complete extraction. Use your judgement:
- Use read_document to understand document structure before extraction.
- Use update_memory to record your observations (document_type, complexity, confidence, notes).
- Use extract_form to map document content to form fields. Pass patches when revising.
- Use review_draft to validate quality — the reviewer reads the original image directly.
- If reviewer approves, call finalize_result with status="success".
- If reviewer returns needs_revision and revision would improve quality, apply patches via extract_form and review again.
- If document is unclear or revision count is high, finalize with status="partial" or "failed".
- For simple, clearly readable documents you may skip review if confidence is high.
- Check your memory state before deciding the next step."""

# ── Supervisor tool definitions (OpenAI function-calling format) ─────────────

SUPERVISOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "Run the document-reader sub-agent. Returns a structured description of the card's sections and content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "png_path": {"type": "string", "description": "Absolute path to the PNG image of the card page"},
                },
                "required": ["png_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_form",
            "description": "Run the form-extractor sub-agent. Maps a DocumentReading into CardData form fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_reading": {"type": "object", "description": "Output from read_document"},
                    "patches": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Optional field_patches from the reviewer to apply in this extraction pass",
                    },
                },
                "required": ["document_reading"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "review_draft",
            "description": "Run the validator-reviewer sub-agent. Compares the form draft against the original image and returns approved / needs_revision / rejected plus field_patches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "png_path": {"type": "string"},
                    "document_reading": {"type": "object"},
                    "draft": {"type": "object"},
                },
                "required": ["png_path", "document_reading", "draft"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_result",
            "description": "End the pipeline and return the final extraction result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "draft": {"type": "object", "description": "The final CardData draft to persist"},
                    "status": {
                        "type": "string",
                        "enum": ["success", "partial", "failed"],
                        "description": "Quality assessment of the final result",
                    },
                },
                "required": ["draft", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": "Update your working memory with observations about this document and extraction progress.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_type": {"type": "string"},
                    "complexity": {
                        "type": "string",
                        "enum": ["simple", "moderate", "complex", "unclear"],
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "notes": {"type": "string"},
                },
            },
        },
    },
]

# ── PDF / image helpers ──────────────────────────────────────────────────────

def _render_pdf_to_png(pdf_path: str, output_path: str, dpi: int = 200) -> None:
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    pix.save(output_path)
    doc.close()


def _png_to_b64(png_path: str) -> str:
    return base64.b64encode(Path(png_path).read_bytes()).decode("ascii")


# ── Cost logging ─────────────────────────────────────────────────────────────

def _log_cost(caller: str, usage: Any, pdf_name: str) -> None:
    tok_in  = getattr(usage, "prompt_tokens", "?")
    tok_out = getattr(usage, "completion_tokens", "?")
    _costs_log.info(
        "%s | caller=%-25s | model=%-30s | in=%-5s out=%-5s | file=%s",
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        caller, settings.agent_model, tok_in, tok_out, pdf_name,
    )


# ── Sub-agent runners ────────────────────────────────────────────────────────
#
# Each runner accepts a shared AsyncOpenAI client and retries once on any
# transient API/network error. Schema keys missing from the LLM response are
# filled with safe defaults and logged as warnings so the supervisor always
# receives a usable dict rather than a hard failure.

def _fill_missing(result: dict, schema: dict, pdf_name: str, agent: str) -> None:
    """Fill required keys absent from result with safe defaults."""
    missing = [k for k in schema.get("required", []) if k not in result]
    if not missing:
        return
    logger.warning("%s missing keys %s for %s — filling defaults", agent, missing, pdf_name)
    array_props = {
        k for k, v in schema.get("properties", {}).items()
        if v.get("type") == "array"
    }
    for k in missing:
        result[k] = [] if k in array_props else None


async def _run_document_reader(client: AsyncOpenAI, png_path: str, pdf_name: str) -> dict:
    png_b64 = _png_to_b64(png_path)
    schema_str = json.dumps(DOCUMENT_READING_SCHEMA, ensure_ascii=False)
    messages = [
        {"role": "system", "content": DOCUMENT_READER_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_b64}"}},
                {"type": "text", "text": f"Analyse this production card. Return JSON matching this schema:\n{schema_str}"},
            ],
        },
    ]
    for attempt in range(2):
        try:
            response = await client.chat.completions.create(
                model=settings.agent_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=2000,
            )
            result = json.loads(response.choices[0].message.content or "{}")
            _log_cost("document-reader", response.usage, pdf_name)
            _fill_missing(result, DOCUMENT_READING_SCHEMA, pdf_name, "document-reader")
            return result
        except Exception as exc:
            if attempt == 1:
                raise
            logger.warning("document-reader attempt 1 failed (%s) for %s, retrying", exc, pdf_name)


async def _run_form_extractor(
    client: AsyncOpenAI,
    document_reading: dict,
    pdf_name: str,
    patches: list[dict] | None = None,
) -> dict:
    reading_json = json.dumps(document_reading, ensure_ascii=False, indent=2)
    schema_str = json.dumps(CARD_DATA_DRAFT_SCHEMA, ensure_ascii=False)

    patch_section = ""
    if patches:
        patch_json = json.dumps(patches, ensure_ascii=False, indent=2)
        patch_section = f"\n\nLIST OF CORRECTIONS (field_patches) to apply:\n{patch_json}"

    task = (
        f"Here is the production card content description (DocumentReading):\n{reading_json}"
        f"{patch_section}\n\n"
        f"Fill in the CardData form. Return JSON matching this schema:\n{schema_str}"
    )
    caller = "form-extractor-revision" if patches else "form-extractor"
    for attempt in range(2):
        try:
            response = await client.chat.completions.create(
                model=settings.agent_model,
                messages=[
                    {"role": "system", "content": FORM_EXTRACTOR_SYSTEM},
                    {"role": "user", "content": task},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=3000,
            )
            result = json.loads(response.choices[0].message.content or "{}")
            _log_cost(caller, response.usage, pdf_name)
            _fill_missing(result, CARD_DATA_DRAFT_SCHEMA, pdf_name, caller)
            return result
        except Exception as exc:
            if attempt == 1:
                raise
            logger.warning("%s attempt 1 failed (%s) for %s, retrying", caller, exc, pdf_name)


async def _run_validator_reviewer(
    client: AsyncOpenAI,
    png_path: str,
    document_reading: dict,
    draft: dict,
    pdf_name: str,
) -> dict:
    png_b64 = _png_to_b64(png_path)
    reading_json = json.dumps(document_reading, ensure_ascii=False, indent=2)
    draft_json = json.dumps(draft, ensure_ascii=False, indent=2)
    schema_str = json.dumps(REVIEW_RESULT_SCHEMA, ensure_ascii=False)
    for attempt in range(2):
        try:
            response = await client.chat.completions.create(
                model=settings.agent_model,
                messages=[
                    {"role": "system", "content": VALIDATOR_REVIEWER_SYSTEM},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_b64}"}},
                            {
                                "type": "text",
                                "text": (
                                    f"DocumentReading:\n{reading_json}\n\n"
                                    f"CardDataDraft:\n{draft_json}\n\n"
                                    f"Check the draft against the image. Return JSON matching this schema:\n{schema_str}"
                                ),
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=2000,
            )
            result = json.loads(response.choices[0].message.content or "{}")
            _log_cost("validator-reviewer", response.usage, pdf_name)
            _fill_missing(result, REVIEW_RESULT_SCHEMA, pdf_name, "validator-reviewer")
            return result
        except Exception as exc:
            if attempt == 1:
                raise
            logger.warning("validator-reviewer attempt 1 failed (%s) for %s, retrying", exc, pdf_name)


# ── Result helpers ───────────────────────────────────────────────────────────

def _finalize(draft: dict, model_label: str) -> dict:
    result = {k: draft.get(k) for k in CARD_FIELDS}
    result["parameters"] = draft.get("parameters") or []
    result["model_used"] = model_label
    _strip_empty(result)
    return result


def _strip_empty(d: dict) -> None:
    for k, v in d.items():
        if isinstance(v, str) and v.strip().lower() in ("", "null", "n/a", "none"):
            d[k] = None


def _fallback(reason: str) -> dict:
    result = {field: None for field in CARD_FIELDS}
    result["parameters"] = []
    result["model_used"] = f"fallback-{reason}"
    return result


# ── Supervisor tool executor ─────────────────────────────────────────────────

async def _execute_tool(
    tool_call: Any,
    client: AsyncOpenAI,
    png_path: str,
    pdf_name: str,
    iteration: int,
) -> tuple[str, str, dict | None, dict | None]:
    """
    Execute one supervisor tool call (OpenAI function-calling format).
    Returns (tool_call_id, result_content_json, finalized_result_or_None, memory_patch_or_None).

    update_memory returns a patch dict instead of mutating working_memory directly,
    so callers can apply patches serially after asyncio.gather() completes.
    """
    tool_name = tool_call.function.name
    tool_input = json.loads(tool_call.function.arguments or "{}")
    logger.info("Supervisor tool=%s iter=%d file=%s", tool_name, iteration, pdf_name)

    try:
        if tool_name == "read_document":
            result = await asyncio.wait_for(
                _run_document_reader(client, tool_input["png_path"], pdf_name),
                timeout=SUBAGENT_TIMEOUT_SECONDS,
            )
            content = json.dumps(result, ensure_ascii=False)

        elif tool_name == "extract_form":
            patches = tool_input.get("patches")
            result = await asyncio.wait_for(
                _run_form_extractor(client, tool_input["document_reading"], pdf_name, patches=patches),
                timeout=SUBAGENT_TIMEOUT_SECONDS,
            )
            content = json.dumps(result, ensure_ascii=False)

        elif tool_name == "review_draft":
            result = await asyncio.wait_for(
                _run_validator_reviewer(
                    client,
                    tool_input["png_path"],
                    tool_input["document_reading"],
                    tool_input["draft"],
                    pdf_name,
                ),
                timeout=SUBAGENT_TIMEOUT_SECONDS,
            )
            content = json.dumps(result, ensure_ascii=False)

        elif tool_name == "update_memory":
            patch = {k: v for k, v in tool_input.items() if v is not None}
            content = json.dumps({"status": "ok"})
            return (tool_call.id, content, None, patch)

        elif tool_name == "finalize_result":
            status = tool_input.get("status", "success")
            model_label = f"{settings.agent_model}/supervisor-llm/{status}"
            finalized = _finalize(tool_input["draft"], model_label)
            logger.info("Supervisor finalized status=%s file=%s", status, pdf_name)
            content = json.dumps({"finalized": True, "status": status})
            return (tool_call.id, content, finalized, None)

        else:
            content = json.dumps({"error": f"Unknown tool: {tool_name}"})

        return (tool_call.id, content, None, None)

    except Exception as exc:
        logger.error("Tool %s failed iter=%d file=%s: %s", tool_name, iteration, pdf_name, exc)
        return (tool_call.id, json.dumps({"error": str(exc)}), None, None)


# ── LLM Supervisor pipeline ──────────────────────────────────────────────────

async def extract_card_data(pdf_path: str) -> dict:
    """
    LLM-supervised pipeline. All calls go through LiteLLM proxy (settings.litellm_base_url).
    Model is selected by settings.agent_model (model_name from litellm_config.yaml).
    The supervisor decides which sub-agents to call and when to finalize.
    """
    pdf_name = Path(pdf_path).name
    png_path = Path(pdf_path).with_suffix(".page0.png")

    try:
        _render_pdf_to_png(pdf_path, str(png_path))
    except Exception as exc:
        logger.error("PDF render failed for %s: %s", pdf_name, exc)
        return _fallback("render-error")

    client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)
    working_memory: dict = {
        "document_type": None,
        "complexity": None,
        "revision_count": 0,
        "confidence": None,
        "notes": "",
    }
    messages: list[dict] = [
        {"role": "system", "content": SUPERVISOR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Extract structured data from the production card. "
                f"The card image is at '{png_path}'. "
                "Coordinate your sub-agents to produce an accurate, complete extraction. "
                f"Your current memory: {json.dumps(working_memory)}"
            ),
        },
    ]

    final_result: dict | None = None

    try:
        logger.info("Supervisor pipeline start: %s model=%s", pdf_name, settings.agent_model)

        for iteration in range(SUPERVISOR_MAX_ITERATIONS):
            response = await client.chat.completions.create(
                model=settings.agent_model,
                messages=messages,
                tools=SUPERVISOR_TOOLS,
                tool_choice="auto",
                max_tokens=4096,
            )

            _log_cost(f"supervisor-iter{iteration}", response.usage, pdf_name)

            msg = response.choices[0].message
            messages.append(msg.model_dump(exclude_unset=True, exclude_none=True))

            if response.choices[0].finish_reason != "tool_calls" or not msg.tool_calls:
                logger.warning(
                    "Supervisor stopped without finalize_result (finish_reason=%s) for %s",
                    response.choices[0].finish_reason, pdf_name,
                )
                break

            # Execute all tool calls in parallel
            raw_results = await asyncio.gather(
                *[_execute_tool(tc, client, str(png_path), pdf_name, iteration)
                  for tc in msg.tool_calls]
            )

            # Apply results serially: memory patches after gather to avoid interleaving writes
            for tc_id, content, finalized, memory_patch in raw_results:
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": content})
                if memory_patch:
                    working_memory.update(memory_patch)
                if finalized is not None:
                    final_result = finalized

            revision_increments = sum(
                1 for tc in msg.tool_calls
                if tc.function.name == "extract_form"
                and json.loads(tc.function.arguments or "{}").get("patches")
            )
            if revision_increments:
                working_memory["revision_count"] = working_memory.get("revision_count", 0) + revision_increments

            # Escalation: inject user hint when revision limit is reached
            if final_result is None and working_memory.get("revision_count", 0) >= 3:
                logger.warning(
                    "Supervisor escalation: revision_count=%d for %s",
                    working_memory["revision_count"], pdf_name,
                )
                messages.append({
                    "role": "user",
                    "content": (
                        f"SYSTEM NOTE: Revision limit reached ({working_memory['revision_count']} revisions). "
                        "Please call finalize_result with the best available draft."
                    ),
                })

            if final_result is not None:
                return final_result

        logger.warning(
            "Supervisor reached max iterations (%d) without finalizing for %s",
            SUPERVISOR_MAX_ITERATIONS, pdf_name,
        )
        return _fallback("supervisor-max-iterations")

    except Exception as exc:
        logger.error("Supervisor pipeline error for %s: %s", pdf_name, exc, exc_info=True)
        return _fallback("supervisor-exception")

    finally:
        await client.aclose()
        png_path.unlink(missing_ok=True)
