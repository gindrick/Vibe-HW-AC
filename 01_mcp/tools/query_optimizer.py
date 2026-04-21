import json
import re
import unicodedata
from typing import Dict, List


def _strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_codes(text: str) -> List[str]:
    return list(dict.fromkeys(re.findall(r"\d+(?:\.\d+)+", text or "")))


def _extract_keywords(text: str, limit: int = 10) -> List[str]:
    tokens = re.findall(r"[\w\-.]+", (text or "").lower())
    filtered: List[str] = []
    stop = {
        "k",
        "cemu",
        "čemu",
        "slouzi",
        "slouží",
        "funkce",
        "co",
        "je",
        "na",
        "the",
        "what",
        "is",
        "for",
        "used",
        "function",
    }
    for token in tokens:
        if len(token) < 3:
            continue
        if token in stop:
            continue
        if token not in filtered:
            filtered.append(token)
        if len(filtered) >= limit:
            break
    return filtered


def _build_variants(query: str, codes: List[str], max_variants: int) -> List[str]:
    variants: List[str] = []

    def add(value: str) -> None:
        cleaned = _normalize_whitespace(value)
        if cleaned and cleaned not in variants:
            variants.append(cleaned)

    base = _normalize_whitespace(query)
    base_ascii = _strip_diacritics(base)

    add(base)
    add(base_ascii)

    for code in codes:
        add(f"k čemu slouží funkce {code}")
        add(f"k cemu slouzi funkce {code}")
        add(f"co dělá funkce {code}")
        add(f"what is function {code} used for")
        add(f"function {code} purpose")

    if not codes:
        add(f"vysvětli význam: {base}")
        add(f"explain the purpose of: {base_ascii}")

    return variants[: max(1, int(max_variants))]


async def optimize_query(
    query: str,
    user_message: str = "",
    max_variants: int = 4,
) -> str:
    normalized = _normalize_whitespace(query)
    codes = _extract_codes(normalized)
    keywords = _extract_keywords(normalized)
    variants = _build_variants(normalized, codes, max_variants=max_variants)

    result: Dict[str, object] = {
        "normalized_query": normalized,
        "query_variants": variants,
        "detected_codes": codes,
        "keywords": keywords,
    }

    if user_message:
        result["user_message_echo"] = user_message

    return json.dumps(result, ensure_ascii=False, indent=2)