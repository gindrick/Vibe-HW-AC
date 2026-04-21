import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

import chromadb
from openai import OpenAI


def _create_openai_client() -> OpenAI:
    base_url = os.getenv("LITELLM_BASE_URL", "http://0.0.0.0:4000")
    api_key = os.getenv("LITELLM_API_KEY", "dummy-key")
    return OpenAI(base_url=base_url, api_key=api_key)


def _embed_query(client: OpenAI, query: str) -> List[float]:
    model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
    response = client.embeddings.create(model=model, input=[query])
    return response.data[0].embedding


def _parse_allowed_source_ids_from_user_message(user_message: str) -> Optional[List[str]]:
    raw = (user_message or "").strip()
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except Exception:
        data = None

    if isinstance(data, dict):
        value = data.get("allowed_source_ids")
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            return normalized
        if isinstance(value, str):
            normalized = [item.strip() for item in value.split(",") if item.strip()]
            return normalized

    marker = "allowed_source_ids="
    if marker in raw:
        tail = raw.split(marker, 1)[1]
        tail = tail.split("\n", 1)[0].strip()
        if tail:
            normalized = [item.strip() for item in tail.split(",") if item.strip()]
            return normalized

    return None


def _build_where_filter(allowed_source_ids: Optional[List[str]]) -> Optional[Dict[str, Any]]:
    if allowed_source_ids is None:
        return None
    normalized = [source_id.strip() for source_id in allowed_source_ids if source_id.strip()]
    if not normalized:
        return {"source_id": "__deny_all__"}
    if len(normalized) == 1:
        return {"source_id": normalized[0]}
    return {"source_id": {"$in": normalized}}


def _format_result(result: Dict[str, Any], applied_filter: Optional[List[str]]) -> str:
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    rows: List[Dict[str, Any]] = []
    for idx, document in enumerate(documents):
        metadata = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
        distance = distances[idx] if idx < len(distances) else None
        rows.append(
            {
                "index": idx + 1,
                "source_id": metadata.get("source_id", ""),
                "file_name": metadata.get("file_name", ""),
                "page": metadata.get("page", ""),
                "distance": distance,
                "document": document,
            }
        )

    return json.dumps(
        {
            "count": len(rows),
            "applied_allowed_source_ids": applied_filter,
            "results": rows,
        },
        ensure_ascii=False,
        indent=2,
    )


def _normalize_query_variants(query: str, query_variants: Optional[List[str]]) -> List[str]:
    variants: List[str] = []

    def add(value: str) -> None:
        cleaned = re.sub(r"\s+", " ", (value or "").strip())
        if cleaned and cleaned not in variants:
            variants.append(cleaned)

    add(query)
    if isinstance(query_variants, list):
        for item in query_variants:
            if isinstance(item, str):
                add(item)
    return variants


def _merge_multi_results(
    result_sets: List[Dict[str, Any]],
    applied_filter: Optional[List[str]],
    n_results: int,
    query_variants: List[str],
) -> str:
    merged: Dict[str, Dict[str, Any]] = {}

    for variant_index, result in enumerate(result_sets):
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        for idx, document in enumerate(documents):
            metadata = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
            distance = distances[idx] if idx < len(distances) else None

            key = "|".join(
                [
                    str(metadata.get("source_id", "")),
                    str(metadata.get("file_name", "")),
                    str(metadata.get("page", "")),
                    str(document),
                ]
            )

            existing = merged.get(key)
            if existing is None:
                merged[key] = {
                    "source_id": metadata.get("source_id", ""),
                    "file_name": metadata.get("file_name", ""),
                    "page": metadata.get("page", ""),
                    "distance": distance,
                    "document": document,
                    "matched_queries": [query_variants[variant_index]],
                    "hit_count": 1,
                }
                continue

            existing_distance = existing.get("distance")
            if isinstance(distance, (int, float)) and (
                not isinstance(existing_distance, (int, float)) or distance < existing_distance
            ):
                existing["distance"] = distance

            if query_variants[variant_index] not in existing["matched_queries"]:
                existing["matched_queries"].append(query_variants[variant_index])
            existing["hit_count"] = int(existing.get("hit_count", 1)) + 1

    rows = list(merged.values())

    def score(item: Dict[str, Any]) -> float:
        distance = item.get("distance")
        distance_component = -float(distance) if isinstance(distance, (int, float)) else -999.0
        hit_bonus = float(item.get("hit_count", 1)) * 0.25
        return distance_component + hit_bonus

    rows.sort(key=score, reverse=True)
    limited = rows[: max(1, int(n_results))]

    for idx, row in enumerate(limited, start=1):
        row["index"] = idx

    return json.dumps(
        {
            "count": len(limited),
            "applied_allowed_source_ids": applied_filter,
            "query_variants": query_variants,
            "results": limited,
        },
        ensure_ascii=False,
        indent=2,
    )


async def query_chroma(
    query: str,
    user_message: str,
    persist_dir: str = ".sharepoint_chroma",
    collection_name: str = "sharepoint_docs",
    n_results: int = 5,
) -> str:
    query_text = (query or "").strip()
    if not query_text:
        return "Error: query is required"

    allowed_source_ids = _parse_allowed_source_ids_from_user_message(user_message)
    where_filter = _build_where_filter(allowed_source_ids)

    client = _create_openai_client()
    embedding = _embed_query(client, query_text)

    persist_path = Path(persist_dir).resolve()
    chroma_client = chromadb.PersistentClient(path=str(persist_path))
    collection = chroma_client.get_or_create_collection(name=collection_name)

    result = collection.query(
        query_embeddings=[embedding],
        n_results=max(1, int(n_results)),
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )
    return _format_result(result, allowed_source_ids)


async def query_chroma_multi(
    query: str,
    user_message: str,
    persist_dir: str = ".sharepoint_chroma",
    collection_name: str = "sharepoint_docs",
    n_results: int = 5,
    query_variants: Optional[List[str]] = None,
    max_per_query: int = 5,
) -> str:
    query_text = (query or "").strip()
    if not query_text:
        return "Error: query is required"

    allowed_source_ids = _parse_allowed_source_ids_from_user_message(user_message)
    where_filter = _build_where_filter(allowed_source_ids)

    variants = _normalize_query_variants(query_text, query_variants)

    client = _create_openai_client()
    embeddings = []
    for variant in variants:
        embeddings.append(_embed_query(client, variant))

    persist_path = Path(persist_dir).resolve()
    chroma_client = chromadb.PersistentClient(path=str(persist_path))
    collection = chroma_client.get_or_create_collection(name=collection_name)

    result_sets: List[Dict[str, Any]] = []
    for embedding in embeddings:
        result_sets.append(
            collection.query(
                query_embeddings=[embedding],
                n_results=max(1, int(max_per_query)),
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        )

    return _merge_multi_results(
        result_sets=result_sets,
        applied_filter=allowed_source_ids,
        n_results=n_results,
        query_variants=variants,
    )
