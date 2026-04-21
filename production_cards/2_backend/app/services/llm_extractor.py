from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)
_costs_log = logging.getLogger("production_cards.costs")


# ---------- Structured output schema ----------

class ParameterItem(BaseModel):
    number: Optional[int] = None
    name: str = ""
    value: str = ""
    unit: str = ""


class CardData(BaseModel):
    title: Optional[str] = None
    date: Optional[str] = None
    line_number: Optional[str] = None
    shift: Optional[str] = None
    operator: Optional[str] = None
    tool: Optional[str] = None
    produced_dimension: Optional[str] = None
    surface_treatment: Optional[str] = None
    article_number: Optional[str] = None
    material_granulate: Optional[str] = None
    coating: Optional[str] = None
    thickness: Optional[str] = None
    width: Optional[str] = None
    u_profile: Optional[str] = None
    surface: Optional[str] = None
    gloss: Optional[str] = None
    parameters: list[ParameterItem] = []
    notes: Optional[str] = None
    footer_processed_by: Optional[str] = None
    footer_approved_by: Optional[str] = None


# ---------- Prompt ----------

SYSTEM_PROMPT = """You are an assistant for extracting data from setup cards of extrusion lines.
You will receive an image of a scanned card and extract structured data from it.
Copy values exactly as they appear on the card. If a field cannot be read or is empty, return null.
Sort parameters in ascending order by number, include all rows of the table.
For each parameter, split the measured value from its unit into separate fields:
  - value: the numeric or textual value only (e.g. "247", "100", "16,97")
  - unit: the unit of measure only (e.g. "°C", "BAR", "rpm") — empty string if no unit."""


# ---------- Helpers ----------

def _render_page_b64(pdf_path: str, dpi: int = 200) -> str:
    import base64
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
    doc.close()
    return b64


_ALIAS_MAP = {
    "gpt-4o-mini":      "gpt-4o-mini",
    "oai-gpt-4.1-nano": "gpt-4.1-nano",
}
_PRICE_PER_1K = {
    "gpt-4o-mini":  (0.000150, 0.000600),
    "gpt-4.1-nano": (0.000100, 0.000400),
    "gpt-4o":       (0.002500, 0.010000),
    "gpt-4.1":      (0.002000, 0.008000),
}


def _calc_cost(model_alias: str, tok_in: int | str, tok_out: int | str) -> str:
    real = _ALIAS_MAP.get(model_alias, model_alias)
    price = next((v for k, v in _PRICE_PER_1K.items() if k in real), None)
    if price and isinstance(tok_in, int) and isinstance(tok_out, int):
        return f"{(tok_in * price[0] + tok_out * price[1]) / 1000:.6f}"
    return "N/A"


# ---------- Main extractor ----------

def extract_card_data(pdf_path: str) -> dict:
    """
    Extract structured card data from a scanned PDF using LiteLLM vision +
    structured output (beta.chat.completions.parse).
    Returns a plain dict with all card fields + model_used key.
    """
    from openai import OpenAI

    try:
        png_b64 = _render_page_b64(pdf_path)
    except Exception as exc:
        logger.error("render failed: %s", exc)
        return _fallback("fallback-render-error")

    client = OpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)

    try:
        response = client.beta.chat.completions.parse(
            model=settings.litellm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{png_b64}"},
                        },
                        {
                            "type": "text",
                            "text": "Extract data from this setup card.",
                        },
                    ],
                },
            ],
            response_format=CardData,
            temperature=0,
            max_tokens=2000,
        )
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return _fallback("fallback-llm-error")

    parsed: CardData | None = response.choices[0].message.parsed
    if parsed is None:
        logger.error("Structured output returned None — refusal or parse error")
        return _fallback("fallback-parse-error")

    usage = response.usage
    tok_in = getattr(usage, "prompt_tokens", "?")
    tok_out = getattr(usage, "completion_tokens", "?")
    tok_tot = getattr(usage, "total_tokens", "?")
    model_used = response.model or settings.litellm_model
    cost_str = _calc_cost(model_used, tok_in, tok_out)

    logger.info("extract_card_data: model=%s in=%s out=%s total=%s cost=%s",
                model_used, tok_in, tok_out, tok_tot, cost_str)
    _costs_log.info(
        "%s | caller=extract_card_data | model=%-20s | in=%-5s out=%-5s total=%-6s | cost_usd=%s | file=%s",
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        model_used, tok_in, tok_out, tok_tot, cost_str, Path(pdf_path).name,
    )

    result = parsed.model_dump()
    result["model_used"] = model_used
    _strip_null_strings(result)
    return result


def _strip_null_strings(d: dict) -> None:
    for k, v in d.items():
        if isinstance(v, str) and v.lower() == "null":
            d[k] = None
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _strip_null_strings(item)


def _fallback(model_used: str) -> dict:
    return CardData().model_dump() | {"model_used": model_used}
