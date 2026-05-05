import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from src.pipelines.sharepoint_ingest import (
    load_env,
    load_source_policies,
    load_sources_config,
    resolve_allowed_sources,
)


def _create_openai_client():
    from openai import OpenAI

    base_url = os.getenv("LITELLM_BASE_URL", "http://0.0.0.0:4000")
    api_key = os.getenv("LITELLM_API_KEY", "dummy-key")
    return OpenAI(base_url=base_url, api_key=api_key)


def _embed_query(client, query: str) -> List[float]:
    model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
    response = client.embeddings.create(model=model, input=[query])
    return response.data[0].embedding


def _build_where_filter(allowed_source_ids: List[str]) -> Optional[Dict[str, Any]]:
    normalized = [source_id.strip() for source_id in allowed_source_ids if source_id.strip()]
    if not normalized:
        return None
    if len(normalized) == 1:
        return {"source_id": normalized[0]}
    return {"source_id": {"$in": normalized}}


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}

    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8"))
        data = json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _extract_groups_from_claims(payload: Dict[str, Any]) -> List[str]:
    groups = payload.get("groups", [])
    if not isinstance(groups, list):
        return []
    return [str(group).strip() for group in groups if str(group).strip()]


def _has_group_overage(payload: Dict[str, Any]) -> bool:
    if payload.get("hasgroups"):
        return True

    claim_names = payload.get("_claim_names", {})
    if isinstance(claim_names, dict) and claim_names.get("groups"):
        return True

    return False


def _fetch_user_groups_from_graph(access_token: str) -> List[str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    url = (
        "https://graph.microsoft.com/v1.0/me/transitiveMemberOf/microsoft.graph.group"
        "?$select=id,displayName"
    )

    result: set[str] = set()
    while url:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        for item in data.get("value", []):
            if not isinstance(item, dict):
                continue
            group_id = str(item.get("id", "")).strip()
            group_name = str(item.get("displayName", "")).strip()
            if group_id:
                result.add(group_id)
            if group_name:
                result.add(group_name)

        url = data.get("@odata.nextLink")

    return sorted(result)


def resolve_user_groups(
    explicit_user_groups: List[str],
    access_token: Optional[str] = None,
) -> List[str]:
    if explicit_user_groups:
        return explicit_user_groups
    if not access_token:
        return []

    payload = _decode_jwt_payload(access_token)
    groups = set(_extract_groups_from_claims(payload))

    if _has_group_overage(payload):
        try:
            groups.update(_fetch_user_groups_from_graph(access_token))
        except Exception:
            pass

    return sorted(group for group in groups if group)


def query_sharepoint_docs(
    query_text: str,
    persist_dir: Path,
    collection_name: str,
    n_results: int,
    allowed_source_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    import chromadb

    if allowed_source_ids is not None and not allowed_source_ids:
        return {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

    client = _create_openai_client()
    embedding = _embed_query(client, query_text)

    chroma = chromadb.PersistentClient(path=str(persist_dir.resolve()))
    collection = chroma.get_or_create_collection(name=collection_name)

    where = _build_where_filter(allowed_source_ids or []) if allowed_source_ids is not None else None
    result = collection.query(
        query_embeddings=[embedding],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    return result


def _print_results(result: Dict[str, Any]) -> None:
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    if not documents:
        print("No documents found for current source filter.")
        return

    for index, doc in enumerate(documents, start=1):
        meta = metadatas[index - 1] if index - 1 < len(metadatas) else {}
        dist = distances[index - 1] if index - 1 < len(distances) else None
        source_id = meta.get("source_id", "") if isinstance(meta, dict) else ""
        file_name = meta.get("file_name", "") if isinstance(meta, dict) else ""
        page = meta.get("page", "") if isinstance(meta, dict) else ""

        print(f"{index}. source={source_id} file={file_name} page={page} distance={dist}")
        print(doc)
        print("-" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query SharePoint vector collection with source-based ACL filtering"
    )
    parser.add_argument("--query", type=str, required=True, help="User query text")
    parser.add_argument("--env", type=str, default=None, help="Path to .env")
    parser.add_argument(
        "--persist",
        type=str,
        default=os.getenv("CHROMA_PERSIST_DIR", ".sharepoint_chroma"),
        help="Directory with Chroma DB",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=os.getenv("CHROMA_COLLECTION", "sharepoint_docs"),
        help="Chroma collection name",
    )
    parser.add_argument(
        "--n-results",
        type=int,
        default=5,
        help="Number of retrieved chunks",
    )
    parser.add_argument(
        "--sources-config",
        type=str,
        default=None,
        help="Path to sources JSON array",
    )
    parser.add_argument(
        "--source-policies",
        type=str,
        default=None,
        help="Path to source policy JSON object",
    )
    parser.add_argument(
        "--user-groups",
        type=str,
        default="",
        help="Comma-separated AAD groups for current user",
    )
    parser.add_argument(
        "--allowed-source-ids",
        type=str,
        default="",
        help="Optional explicit source_id allowlist override",
    )
    parser.add_argument(
        "--entra-access-token",
        type=str,
        default="",
        help="Optional delegated Entra access token (JWT) used to auto-resolve user groups",
    )
    parser.add_argument(
        "--access-token-env-var",
        type=str,
        default="AAD_USER_ACCESS_TOKEN",
        help="Environment variable name for delegated Entra access token",
    )
    parser.add_argument(
        "--print-resolved-groups",
        action="store_true",
        help="Print resolved groups and continue",
    )

    args = parser.parse_args()
    load_env(Path(args.env) if args.env else None)

    explicit_ids = [value.strip() for value in args.allowed_source_ids.split(",") if value.strip()]
    explicit_user_groups = [value.strip() for value in args.user_groups.split(",") if value.strip()]

    token_from_env = os.getenv(args.access_token_env_var, "").strip()
    access_token = (args.entra_access_token or token_from_env).strip()
    user_groups = resolve_user_groups(explicit_user_groups=explicit_user_groups, access_token=access_token)

    if args.print_resolved_groups:
        for group in user_groups:
            print(group)

    if explicit_ids:
        allowed_source_ids = explicit_ids
    elif args.sources_config:
        sources = load_sources_config(Path(args.sources_config))
        policies = load_source_policies(Path(args.source_policies)) if args.source_policies else {}
        allowed_source_ids = resolve_allowed_sources(
            sources,
            user_groups,
            policies if policies else None,
        )
    else:
        allowed_source_ids = None

    result = query_sharepoint_docs(
        query_text=args.query,
        persist_dir=Path(args.persist),
        collection_name=args.collection,
        n_results=args.n_results,
        allowed_source_ids=allowed_source_ids,
    )
    _print_results(result)


if __name__ == "__main__":
    main()
