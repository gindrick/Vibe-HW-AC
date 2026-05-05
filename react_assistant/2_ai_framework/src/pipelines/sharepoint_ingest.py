import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Optional
from urllib.parse import urlparse, parse_qs, unquote

import requests
from dotenv import load_dotenv


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _iter_pdf_pages(file_path: Path) -> Iterable[Tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        yield idx, text


def _extract_docx_text(file_path: Path) -> str:
    import importlib

    docx_module = importlib.import_module("docx")
    document = docx_module.Document(str(file_path))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text]
    return "\n".join([paragraph for paragraph in paragraphs if paragraph])


def _extract_doc_text_fallback(file_path: Path) -> str:
    if os.name != "nt":
        return ""

    try:
        import win32com.client  # type: ignore
    except Exception:
        return ""

    word = None
    doc = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(file_path.resolve()))
        content = str(doc.Content.Text or "")
        return content.strip()
    except Exception:
        return ""
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    if not text:
        return []
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = max(0, end - overlap)
    return chunks


def _load_manifest(manifest_path: Path) -> Dict[str, Dict[str, float]]:
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _save_manifest(manifest_path: Path, data: Dict[str, Dict[str, float]]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_json_map(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_json_map(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _file_signature(file_path: Path) -> Dict[str, float]:
    stat = file_path.stat()
    return {"mtime": stat.st_mtime, "size": stat.st_size}


def _needs_update(manifest: Dict[str, Dict[str, float]], file_path: Path) -> bool:
    key = str(file_path)
    current = _file_signature(file_path)
    cached = manifest.get(key)
    return cached != current


def _list_files(source_dir: Path, extensions: List[str]) -> List[Path]:
    files: List[Path] = []
    for ext in extensions:
        files.extend(source_dir.rglob(f"*.{ext}"))
    return files


def _create_openai_client():
    from openai import OpenAI

    base_url = os.getenv("LITELLM_BASE_URL", "http://0.0.0.0:4000")
    api_key = os.getenv("LITELLM_API_KEY", "dummy-key")
    return OpenAI(base_url=base_url, api_key=api_key)


def _embed_texts(client, texts: List[str]) -> List[List[float]]:
    model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


def load_env(env_path: Optional[Path]) -> None:
    if env_path is None:
        default_env = Path(__file__).parent / ".env"
        if default_env.exists():
            load_dotenv(default_env, override=True)
            _load_env_fallback(default_env)
        return
    if not env_path.exists():
        raise RuntimeError(f".env file not found: {env_path}")
    load_dotenv(env_path, override=True)
    _load_env_fallback(env_path)


def _load_env_fallback(env_path: Path) -> None:
    if os.getenv("SHAREPOINT_SITE_URL"):
        return

    try:
        raw_bytes = env_path.read_bytes()
    except Exception:
        return

    if b"\x00" in raw_bytes:
        content = raw_bytes.replace(b"\x00", b"").decode("utf-8", errors="ignore")
    else:
        content = raw_bytes.decode("utf-8", errors="ignore")
    if not content:
        return

    for line in content.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        if key and value is not None:
            if not os.getenv(key):
                os.environ[key] = value


def _get_graph_token() -> str:
    tenant_id = os.getenv("AZURE_TENANT_ID", "").strip()
    client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
    client_secret = os.getenv("AZURE_CLIENT_SECRET", "").strip()

    if not tenant_id or not client_id or not client_secret:
        raise RuntimeError("Missing Azure AD credentials in environment")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    response = requests.post(token_url, data=data, timeout=30)
    response.raise_for_status()
    return response.json()["access_token"]


def _graph_get(url: str, token: str, params: Optional[Dict[str, str]] = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _graph_get_paged(
    url: str,
    token: str,
    params: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    next_url: Optional[str] = url
    next_params = params

    while next_url:
        data = _graph_get(next_url, token, params=next_params)
        value = data.get("value", [])
        if isinstance(value, list):
            items.extend([item for item in value if isinstance(item, dict)])
        next_url = data.get("@odata.nextLink")
        next_params = None
    return items


def _graph_get_paged_with_delta(
    url: str,
    token: str,
    params: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    items: List[Dict[str, Any]] = []
    delta_link = ""
    next_url: Optional[str] = url
    next_params = params

    while next_url:
        data = _graph_get(next_url, token, params=next_params)
        value = data.get("value", [])
        if isinstance(value, list):
            items.extend([item for item in value if isinstance(item, dict)])

        next_url = data.get("@odata.nextLink")
        if isinstance(data.get("@odata.deltaLink"), str):
            delta_link = str(data.get("@odata.deltaLink"))
        next_params = None

    return items, delta_link


def _resolve_site_id(site_url: str, token: str) -> Tuple[str, str, str]:
    parsed = urlparse(site_url)
    hostname = parsed.netloc
    site_path = parsed.path.rstrip("/")
    url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}"
    data = _graph_get(url, token)
    return data["id"], hostname, site_path


def _resolve_drive_id(site_id: str, drive_name: str, token: str) -> str:
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    data = _graph_get(url, token)
    drives = data.get("value", [])
    for drive in drives:
        if drive.get("name", "").lower() == drive_name.lower():
            return drive["id"]
    if not drives:
        raise RuntimeError("No drives found for site")
    return drives[0]["id"]


def _resolve_source_context(
    site_url: str,
    drive_name: str,
    folder_path_raw: str,
    token: Optional[str] = None,
) -> Dict[str, str]:
    active_token = token or _get_graph_token()
    site_id, _hostname, site_path = _resolve_site_id(site_url, active_token)
    drive_id = _resolve_drive_id(site_id, drive_name, active_token)
    folder_path = _normalize_folder_path(folder_path_raw, site_path)
    return {
        "token": active_token,
        "site_id": site_id,
        "drive_id": drive_id,
        "site_path": site_path,
        "folder_path": folder_path,
    }


def _normalize_folder_path(raw: str, site_path: str) -> str:
    value = raw.strip()
    if not value:
        return ""

    if value.startswith("http"):
        parsed = urlparse(value)
        query = parse_qs(parsed.query)
        if "id" in query:
            value = unquote(query["id"][0])
        else:
            value = parsed.path

    # Remove site prefix if present
    if site_path and value.startswith(site_path):
        value = value[len(site_path) :]

    value = value.lstrip("/")

    # Default Documents drive maps to "Shared Documents"
    shared_prefix = "Shared Documents/"
    if value.startswith(shared_prefix):
        value = value[len(shared_prefix) :]

    return value.rstrip("/")


def resolve_source_id(source: Dict[str, Any]) -> str:
    existing = str(source.get("source_id", "")).strip()
    if existing:
        return existing

    site_url = str(source.get("site_url", "")).strip().lower()
    drive_name = str(source.get("drive_name", "Documents")).strip().lower()
    folder_path = str(source.get("folder_path", "")).strip().lower()
    return f"src_{_sha1(f'{site_url}|{drive_name}|{folder_path}')[:12]}"


def load_sources_config(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"sources config file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError("sources config must be a JSON array")

    sources: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("enabled", True) is False:
            continue

        site_url = str(item.get("site_url", "")).strip()
        if not site_url:
            raise RuntimeError("Each source in sources config must include site_url")

        source: Dict[str, Any] = {
            "source_id": resolve_source_id(item),
            "site_url": site_url,
            "drive_name": str(item.get("drive_name", "Documents")).strip() or "Documents",
            "folder_path": str(item.get("folder_path", "")).strip(),
            "source_dir": str(item.get("source_dir", item.get("local_source_dir", ""))).strip(),
            "allowed_aad_groups": item.get("allowed_aad_groups", []) or [],
            "enabled": True,
        }
        sources.append(source)
    return sources


def load_source_policies(path: Optional[Path]) -> Dict[str, List[str]]:
    if path is None:
        return {}
    if not path.exists():
        raise RuntimeError(f"source policies file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("source policies config must be a JSON object")

    policies: Dict[str, List[str]] = {}
    for source_id, groups in raw.items():
        if not isinstance(source_id, str):
            continue
        if not isinstance(groups, list):
            continue
        normalized = [str(g).strip() for g in groups if str(g).strip()]
        policies[source_id] = normalized
    return policies


def resolve_allowed_sources(
    sources: List[Dict[str, Any]],
    user_groups: List[str],
    policies: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    normalized_groups = {g.strip().lower() for g in user_groups if g.strip()}
    allowed: List[str] = []

    for source in sources:
        source_id = str(source.get("source_id", "")).strip()
        if not source_id:
            continue

        configured_groups = (
            (policies or {}).get(source_id)
            if policies is not None and source_id in (policies or {})
            else source.get("allowed_aad_groups", [])
        )
        if not configured_groups:
            allowed.append(source_id)
            continue

        allowed_groups = {
            str(group).strip().lower() for group in configured_groups if str(group).strip()
        }
        if normalized_groups.intersection(allowed_groups):
            allowed.append(source_id)
    return allowed


def list_sharepoint_items(
    site_url: Optional[str] = None,
    drive_name: Optional[str] = None,
    folder_path_raw: Optional[str] = None,
) -> List[Dict[str, object]]:
    site_url = (site_url or os.getenv("SHAREPOINT_SITE_URL", "")).strip()
    drive_name = (drive_name or os.getenv("SHAREPOINT_DRIVE_NAME", "Documents")).strip()
    folder_path_raw = (folder_path_raw or os.getenv("SHAREPOINT_FOLDER_PATH", "")).strip()

    if not site_url:
        raise RuntimeError("Missing SHAREPOINT_SITE_URL in environment")

    context = _resolve_source_context(site_url, drive_name, folder_path_raw)
    token = context["token"]
    drive_id = context["drive_id"]
    folder_path = context["folder_path"]

    if folder_path:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}:/children"
    else:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"

    return _graph_get_paged(url, token)


def sync_sharepoint_files_to_local(
    site_url: str,
    drive_name: str,
    folder_path_raw: str,
    target_dir: Path,
    max_items: int = 0,
    overwrite: bool = False,
    state_path: Optional[Path] = None,
    source_id: str = "default",
    use_delta: bool = True,
    reset_delta: bool = False,
) -> Dict[str, int]:
    context = _resolve_source_context(site_url, drive_name, folder_path_raw)
    token = context["token"]
    drive_id = context["drive_id"]
    folder_path = context["folder_path"]

    sync_state_path = state_path or (target_dir / ".sharepoint_sync_state.json")
    sync_state = _load_json_map(sync_state_path)
    source_state_raw = sync_state.get(source_id, {})
    source_state = source_state_raw if isinstance(source_state_raw, dict) else {}
    item_index_raw = source_state.get("item_index", {})
    item_index = item_index_raw if isinstance(item_index_raw, dict) else {}
    delta_link = "" if reset_delta else str(source_state.get("delta_link", "")).strip()

    items: List[Dict[str, Any]]
    new_delta_link = delta_link

    if use_delta:
        if delta_link:
            items, new_delta_link = _graph_get_paged_with_delta(delta_link, token)
        else:
            if folder_path:
                delta_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}:/delta"
            else:
                delta_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/delta"
            items, new_delta_link = _graph_get_paged_with_delta(delta_url, token)
    else:
        if folder_path:
            list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}:/children"
        else:
            list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"
        items = _graph_get_paged(list_url, token)
        if max_items > 0:
            items = items[:max_items]

    target_dir.mkdir(parents=True, exist_ok=True)

    listed = 0
    downloaded = 0
    skipped = 0
    failed = 0
    deleted_local = 0
    repaired_local = 0

    for item in items:
        if not isinstance(item, dict):
            continue

        item_id = str(item.get("id", "")).strip()
        if not item_id:
            continue

        if item.get("deleted"):
            known = item_index.get(item_id, {})
            known_name = ""
            if isinstance(known, dict):
                known_name = str(known.get("name", "")).strip()
            item_name = str(item.get("name", "")).strip() or known_name
            if item_name:
                local_path = target_dir / item_name
                if local_path.exists():
                    try:
                        local_path.unlink()
                        deleted_local += 1
                    except Exception:
                        pass
            item_index.pop(item_id, None)
            continue

        if "file" not in item:
            continue

        listed += 1
        item_name = str(item.get("name", "")).strip()
        if not item_name:
            continue

        previous = item_index.get(item_id, {})
        previous_name = ""
        if isinstance(previous, dict):
            previous_name = str(previous.get("name", "")).strip()
        if previous_name and previous_name != item_name:
            old_path = target_dir / previous_name
            if old_path.exists():
                try:
                    old_path.unlink()
                    deleted_local += 1
                except Exception:
                    pass

        item_index[item_id] = {
            "name": item_name,
            "size": item.get("size", 0),
            "lastModifiedDateTime": item.get("lastModifiedDateTime", ""),
            "web_url": str(item.get("webUrl", "")).strip(),
            "sharepoint_url": str(item.get("webUrl", "")).strip(),
        }

        local_path = target_dir / item_name
        if local_path.exists() and not overwrite:
            skipped += 1
            continue

        try:
            download_url = str(item.get("@microsoft.graph.downloadUrl", "")).strip()
            if download_url:
                response = requests.get(download_url, timeout=120)
            else:
                content_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content"
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.get(content_url, headers=headers, timeout=120)

            response.raise_for_status()
            local_path.write_bytes(response.content)
            downloaded += 1
        except Exception:
            failed += 1

    if use_delta and item_index:
        for known_item_id, known in list(item_index.items()):
            if not isinstance(known, dict):
                continue
            known_name = str(known.get("name", "")).strip()
            if not known_name:
                continue
            local_path = target_dir / known_name
            if local_path.exists():
                continue

            try:
                content_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{known_item_id}/content"
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.get(content_url, headers=headers, timeout=120)
                response.raise_for_status()
                local_path.write_bytes(response.content)
                repaired_local += 1
            except Exception:
                failed += 1

    source_state = {
        "delta_link": new_delta_link,
        "item_index": item_index,
        "updated_at": _utc_now_iso(),
        "mode": "delta" if use_delta else "full",
    }
    sync_state[source_id] = source_state
    _save_json_map(sync_state_path, sync_state)

    return {
        "listed": listed,
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "deleted_local": deleted_local,
        "repaired_local": repaired_local,
    }


def _extract_permission_subjects(permission: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, str]]]:
    subjects: set[str] = set()
    groups: Dict[str, Dict[str, str]] = {}

    def _add_subjects(payload: Any) -> None:
        if not isinstance(payload, dict):
            return

        user = payload.get("user")
        if isinstance(user, dict):
            email = str(user.get("email", "")).strip()
            name = str(user.get("displayName", "")).strip()
            if email:
                subjects.add(email)
            elif name:
                subjects.add(name)

        group = payload.get("group")
        if isinstance(group, dict):
            name = str(group.get("displayName", "")).strip()
            group_id = str(group.get("id", "")).strip()
            if name and group_id:
                subjects.add(f"group:{name} ({group_id})")
                groups[group_id] = {"id": group_id, "name": name}
            elif name:
                subjects.add(f"group:{name}")
            elif group_id:
                subjects.add(f"group:{group_id}")
                groups[group_id] = {"id": group_id, "name": ""}

        app = payload.get("application")
        if isinstance(app, dict):
            name = str(app.get("displayName", "")).strip()
            app_id = str(app.get("id", "")).strip()
            if name and app_id:
                subjects.add(f"app:{name} ({app_id})")
            elif name:
                subjects.add(f"app:{name}")
            elif app_id:
                subjects.add(f"app:{app_id}")

    for key in ("grantedTo", "grantedToV2"):
        _add_subjects(permission.get(key))

    for key in ("grantedToIdentities", "grantedToIdentitiesV2"):
        identities = permission.get(key, [])
        if isinstance(identities, list):
            for identity in identities:
                _add_subjects(identity)

    link = permission.get("link")
    if isinstance(link, dict):
        scope = str(link.get("scope", "")).strip()
        link_type = str(link.get("type", "")).strip()
        if scope or link_type:
            subjects.add(f"link:{scope or 'unknown'}:{link_type or 'unknown'}")

    return sorted(subjects), sorted(groups.values(), key=lambda value: value.get("id", ""))


def _expand_group_members(group_id: str, token: str) -> Tuple[List[str], str]:
    url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/transitiveMembers"
    params = {"$select": "id,displayName,mail,userPrincipalName"}

    try:
        members = _graph_get_paged(url, token, params=params)
    except Exception as exc:
        return [], str(exc)

    resolved: set[str] = set()
    for member in members:
        upn = str(member.get("userPrincipalName", "")).strip()
        mail = str(member.get("mail", "")).strip()
        display_name = str(member.get("displayName", "")).strip()
        member_id = str(member.get("id", "")).strip()

        if upn:
            resolved.add(upn)
        elif mail:
            resolved.add(mail)
        elif display_name and member_id:
            resolved.add(f"{display_name} ({member_id})")
        elif display_name:
            resolved.add(display_name)
        elif member_id:
            resolved.add(member_id)

    return sorted(resolved), ""


def get_sharepoint_item_permissions(
    site_url: str,
    drive_name: str,
    folder_path_raw: str,
    max_items: int = 0,
    expand_group_members: bool = False,
) -> List[Dict[str, Any]]:
    token = _get_graph_token()
    site_id, _hostname, site_path = _resolve_site_id(site_url, token)
    drive_id = _resolve_drive_id(site_id, drive_name, token)
    folder_path = _normalize_folder_path(folder_path_raw, site_path)

    if folder_path:
        list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}:/children"
    else:
        list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"

    items = _graph_get_paged(list_url, token)
    if max_items > 0:
        items = items[:max_items]

    results: List[Dict[str, Any]] = []
    for item in items:
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            continue

        permissions_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/permissions"
        try:
            permissions = _graph_get_paged(permissions_url, token)
            subjects: set[str] = set()
            groups: Dict[str, Dict[str, str]] = {}
            for permission in permissions:
                permission_subjects, permission_groups = _extract_permission_subjects(permission)
                subjects.update(permission_subjects)
                for group in permission_groups:
                    group_id = str(group.get("id", "")).strip()
                    if group_id:
                        groups[group_id] = group

            expanded_members: Dict[str, List[str]] = {}
            expand_errors: Dict[str, str] = {}
            if expand_group_members:
                for group_id, group in groups.items():
                    members, error = _expand_group_members(group_id, token)
                    group_name = str(group.get("name", "")).strip()
                    group_key = f"{group_name} ({group_id})" if group_name else group_id
                    if error:
                        expand_errors[group_key] = error
                    elif members:
                        expanded_members[group_key] = members

            results.append(
                {
                    "item": item,
                    "allowed_subjects": sorted(subjects),
                    "resolved_group_users": expanded_members,
                    "group_expand_errors": expand_errors,
                    "permissions_count": len(permissions),
                    "error": "",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "item": item,
                    "allowed_subjects": [],
                    "resolved_group_users": {},
                    "group_expand_errors": {},
                    "permissions_count": 0,
                    "error": str(exc),
                }
            )

    return results


def _write_sp_list_log(
    items: List[Dict[str, object]],
    log_path: Path,
    source_id: Optional[str] = None,
    append: bool = False,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now_iso()
    heading = f"# SharePoint listing @ {timestamp}"
    if source_id:
        heading = f"{heading} | source_id={source_id}"
    lines = [heading]
    for item in items:
        name = item.get("name", "")
        web_url = item.get("webUrl", "")
        size = item.get("size", 0)
        lines.append(f"{name} | {web_url} | {size} bytes")
    mode = "a" if append and log_path.exists() else "w"
    with log_path.open(mode, encoding="utf-8") as handle:
        if mode == "a":
            handle.write("\n")
        handle.write("\n".join(lines) + "\n")


def _write_sp_permissions_log(
    entries: List[Dict[str, Any]],
    log_path: Path,
    source_id: Optional[str] = None,
    append: bool = False,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now_iso()
    heading = f"# SharePoint permissions @ {timestamp}"
    if source_id:
        heading = f"{heading} | source_id={source_id}"
    lines = [heading]

    for entry in entries:
        item = entry.get("item", {}) if isinstance(entry, dict) else {}
        if not isinstance(item, dict):
            item = {}
        name = item.get("name", "")
        web_url = item.get("webUrl", "")
        subjects = entry.get("allowed_subjects", []) if isinstance(entry, dict) else []
        resolved_group_users = (
            entry.get("resolved_group_users", {}) if isinstance(entry, dict) else {}
        )
        group_expand_errors = entry.get("group_expand_errors", {}) if isinstance(entry, dict) else {}
        error = str(entry.get("error", "")) if isinstance(entry, dict) else ""

        if error:
            lines.append(f"{name} | {web_url} | ERROR: {error}")
            continue

        if not isinstance(subjects, list):
            subjects = []
        subjects_text = "; ".join(str(s) for s in subjects if str(s).strip()) or "<none-resolved>"
        line = f"{name} | {web_url} | allowed: {subjects_text}"

        if isinstance(resolved_group_users, dict) and resolved_group_users:
            groups_text_parts: List[str] = []
            for group_key, users in resolved_group_users.items():
                if not isinstance(users, list):
                    continue
                users_text = ", ".join(str(user) for user in users if str(user).strip())
                groups_text_parts.append(f"{group_key} => [{users_text}]")
            if groups_text_parts:
                line = f"{line} | expanded_users: {'; '.join(groups_text_parts)}"

        if isinstance(group_expand_errors, dict) and group_expand_errors:
            errors_text = "; ".join(
                f"{key}: {value}" for key, value in group_expand_errors.items()
            )
            if errors_text:
                line = f"{line} | expand_errors: {errors_text}"

        lines.append(line)

    mode = "a" if append and log_path.exists() else "w"
    with log_path.open(mode, encoding="utf-8") as handle:
        if mode == "a":
            handle.write("\n")
        handle.write("\n".join(lines) + "\n")


def _write_skipped_files_log(
    entries: List[Dict[str, str]],
    log_path: Path,
    source_id: Optional[str] = None,
    append: bool = False,
) -> None:
    if not entries:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now_iso()
    heading = f"# SharePoint ingest skipped files @ {timestamp}"
    if source_id:
        heading = f"{heading} | source_id={source_id}"
    lines = [heading]

    for entry in entries:
        file_name = str(entry.get("file_name", "")).strip()
        file_path = str(entry.get("file_path", "")).strip()
        reason = str(entry.get("reason", "")).strip() or "unknown"
        detail = str(entry.get("detail", "")).strip()
        line = f"{file_name} | {file_path} | reason: {reason}"
        if detail:
            line = f"{line} | detail: {detail}"
        lines.append(line)

    mode = "a" if append and log_path.exists() else "w"
    with log_path.open(mode, encoding="utf-8") as handle:
        if mode == "a":
            handle.write("\n")
        handle.write("\n".join(lines) + "\n")


def _resolve_log_path(cli_value: Optional[str]) -> Optional[Path]:
    candidate = (cli_value or os.getenv("SP_LIST_LOG_PATH", "")).strip()
    if not candidate:
        return None
    return Path(candidate)


def _load_source_web_urls_from_sync_state(persist_dir: Path, source_id: str) -> Dict[str, str]:
    sync_state_path = persist_dir / "sharepoint_sync_state.json"
    sync_state = _load_json_map(sync_state_path)
    source_state_raw = sync_state.get(source_id, {})
    source_state = source_state_raw if isinstance(source_state_raw, dict) else {}
    item_index_raw = source_state.get("item_index", {})
    item_index = item_index_raw if isinstance(item_index_raw, dict) else {}

    mapping: Dict[str, str] = {}
    for item in item_index.values():
        if not isinstance(item, dict):
            continue

        file_name = str(item.get("name", "")).strip()
        if not file_name:
            continue

        web_url = str(item.get("sharepoint_url", "") or item.get("web_url", "") or item.get("webUrl", "")).strip()
        if web_url:
            mapping[file_name] = web_url

    return mapping


def ingest_sharepoint_docs(
    source_dir: Path,
    persist_dir: Path,
    collection_name: str,
    extensions: List[str],
    batch_size: int = 64,
    source_id: str = "default",
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> List[Dict[str, str]]:
    source_dir = source_dir.resolve()
    persist_dir = persist_dir.resolve()

    client = _create_openai_client()
    import chromadb

    chroma = chromadb.PersistentClient(path=str(persist_dir))
    collection = chroma.get_or_create_collection(name=collection_name)

    manifest_path = persist_dir / "sharepoint_manifest.json"
    manifest_data = _load_manifest(manifest_path)

    is_legacy_manifest = bool(manifest_data) and all(
        isinstance(value, dict) and "mtime" in value and "size" in value
        for value in manifest_data.values()
    )
    if is_legacy_manifest:
        manifest_data = {source_id: manifest_data}

    source_manifest = manifest_data.get(source_id, {})
    if not isinstance(source_manifest, dict):
        source_manifest = {}

    source_web_urls = _load_source_web_urls_from_sync_state(persist_dir=persist_dir, source_id=source_id)

    files = _list_files(source_dir, extensions)
    skipped_entries: List[Dict[str, str]] = []

    # Remove deleted files from index
    existing = {str(p) for p in files}
    for cached_path in list(source_manifest.keys()):
        if cached_path not in existing:
            file_id = _sha1(f"{source_id}:{cached_path}")
            collection.delete(
                where={
                    "$and": [
                        {"file_id": file_id},
                        {"source_id": source_id},
                    ]
                }
            )
            source_manifest.pop(cached_path, None)

    for file_path in files:
        if not _needs_update(source_manifest, file_path):
            continue

        file_id = _sha1(f"{source_id}:{file_path}")
        collection.delete(
            where={
                "$and": [
                    {"file_id": file_id},
                    {"source_id": source_id},
                ]
            }
        )

        docs: List[str] = []
        ids: List[str] = []
        metadatas: List[Dict[str, object]] = []

        suffix = file_path.suffix.lower()
        sharepoint_url = source_web_urls.get(file_path.name, "")

        if suffix == ".pdf":
            try:
                for page_num, page_text in _iter_pdf_pages(file_path):
                    for chunk_idx, chunk in enumerate(
                        _chunk_text(page_text, chunk_size=chunk_size, overlap=chunk_overlap)
                    ):
                        doc_id = _sha1(f"{file_id}:{page_num}:{chunk_idx}")
                        docs.append(chunk)
                        ids.append(doc_id)
                        metadatas.append(
                            {
                                "file_id": file_id,
                                "source_id": source_id,
                                "file_path": str(file_path),
                                "file_name": file_path.name,
                                "page": page_num,
                                "chunk": chunk_idx,
                                **({"sharepoint_url": sharepoint_url} if sharepoint_url else {}),
                            }
                        )
            except Exception as exc:
                skipped_entries.append(
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "reason": "extract_failed",
                        "detail": str(exc),
                    }
                )
                continue
        elif suffix == ".docx":
            try:
                text = _extract_docx_text(file_path)
            except Exception as exc:
                skipped_entries.append(
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "reason": "extract_failed",
                        "detail": str(exc),
                    }
                )
                continue
            for chunk_idx, chunk in enumerate(
                _chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
            ):
                doc_id = _sha1(f"{file_id}:docx:{chunk_idx}")
                docs.append(chunk)
                ids.append(doc_id)
                metadatas.append(
                    {
                        "file_id": file_id,
                        "source_id": source_id,
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "page": 0,
                        "chunk": chunk_idx,
                        **({"sharepoint_url": sharepoint_url} if sharepoint_url else {}),
                    }
                )
        elif suffix == ".doc":
            text = _extract_doc_text_fallback(file_path)
            if not text.strip():
                skipped_entries.append(
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "reason": "extract_failed_or_empty",
                        "detail": "DOC fallback extractor did not return text",
                    }
                )
                continue
            for chunk_idx, chunk in enumerate(
                _chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
            ):
                doc_id = _sha1(f"{file_id}:doc:{chunk_idx}")
                docs.append(chunk)
                ids.append(doc_id)
                metadatas.append(
                    {
                        "file_id": file_id,
                        "source_id": source_id,
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "page": 0,
                        "chunk": chunk_idx,
                        **({"sharepoint_url": sharepoint_url} if sharepoint_url else {}),
                    }
                )
        else:
            skipped_entries.append(
                {
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "reason": "unsupported_extension",
                    "detail": suffix,
                }
            )
            continue

        if not docs:
            skipped_entries.append(
                {
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "reason": "empty_text",
                    "detail": "No chunks extracted",
                }
            )
            continue

        # Batch embeddings + upsert
        for i in range(0, len(docs), batch_size):
            batch_docs = docs[i : i + batch_size]
            batch_ids = ids[i : i + batch_size]
            batch_meta = metadatas[i : i + batch_size]
            embeddings = _embed_texts(client, batch_docs)
            collection.add(
                documents=batch_docs,
                ids=batch_ids,
                metadatas=batch_meta,
                embeddings=embeddings,
            )

        source_manifest[str(file_path)] = _file_signature(file_path)

    manifest_data[source_id] = source_manifest
    _save_manifest(manifest_path, manifest_data)
    return skipped_entries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest SharePoint documents into a local vector DB"
    )
    parser.set_defaults(sync_use_delta=True)
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Path to .env with SharePoint/Graph settings",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="List SharePoint files via Graph API and exit",
    )
    parser.add_argument(
        "--debug-env",
        action="store_true",
        help="Print which SharePoint env vars are set (without values)",
    )
    parser.add_argument(
        "--sp-list-log",
        type=str,
        default=None,
        help="Path to write SharePoint folder listing log",
    )
    parser.add_argument(
        "--sp-permissions-log",
        type=str,
        default=None,
        help="Path to write per-document permissions log",
    )
    parser.add_argument(
        "--include-permissions",
        action="store_true",
        help="Fetch and log SharePoint item permissions for each listed document",
    )
    parser.add_argument(
        "--permissions-max-items",
        type=int,
        default=0,
        help="Limit number of items for permissions export (0 = all listed items)",
    )
    parser.add_argument(
        "--expand-group-members",
        action="store_true",
        help="Expand group permissions to member users where Graph allows it",
    )
    parser.add_argument(
        "--sync-files",
        action="store_true",
        help="Download SharePoint files into local source_dir before ingest",
    )
    parser.add_argument(
        "--sync-max-items",
        type=int,
        default=0,
        help="Limit number of files downloaded per source (0 = all files)",
    )
    parser.add_argument(
        "--overwrite-local-files",
        action="store_true",
        help="Overwrite already downloaded local files during sync",
    )
    parser.add_argument(
        "--sync-state",
        type=str,
        default=None,
        help="Path to sync state file with deltaLink and item index",
    )
    parser.add_argument(
        "--sync-use-delta",
        dest="sync_use_delta",
        action="store_true",
        help="Use Graph delta endpoint for incremental SharePoint sync (default)",
    )
    parser.add_argument(
        "--no-sync-delta",
        dest="sync_use_delta",
        action="store_false",
        help="Disable Graph delta endpoint and use full listing sync",
    )
    parser.add_argument(
        "--sync-reset-delta",
        action="store_true",
        help="Ignore stored delta token and start new delta baseline",
    )
    parser.add_argument(
        "--skipped-log",
        type=str,
        default=None,
        help="Path to write skipped-file details from ingest",
    )
    parser.add_argument(
        "--source",
        type=str,
        required=False,
        help="Local folder with SharePoint files (mirrored/manual export)",
    )
    parser.add_argument(
        "--sources-config",
        type=str,
        default=None,
        help="Path to JSON array of SharePoint sources for multi-site/multi-folder ingest",
    )
    parser.add_argument(
        "--source-policies",
        type=str,
        default=None,
        help="Path to JSON object mapping source_id -> allowed AAD groups",
    )
    parser.add_argument(
        "--user-groups",
        type=str,
        default="",
        help="Comma-separated AAD groups for access-evaluation preview",
    )
    parser.add_argument(
        "--print-allowed-sources",
        action="store_true",
        help="Print source_ids allowed for --user-groups and exit",
    )
    parser.add_argument(
        "--persist",
        type=str,
        default=".sharepoint_chroma",
        help="Directory to persist Chroma DB",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="sharepoint_docs",
        help="Chroma collection name",
    )
    parser.add_argument(
        "--extensions",
        type=str,
        default="pdf",
        help="Comma-separated list of extensions to ingest",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1200,
        help="Chunk size for text splitting",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="Chunk overlap for text splitting",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch for changes by periodic rescans",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Watch interval in seconds",
    )

    args = parser.parse_args()

    load_env(Path(args.env) if args.env else None)

    sources_config = Path(args.sources_config) if args.sources_config else None

    if args.debug_env:
        keys = [
            "AZURE_TENANT_ID",
            "AZURE_CLIENT_ID",
            "AZURE_CLIENT_SECRET",
            "SHAREPOINT_SITE_URL",
            "SHAREPOINT_DRIVE_NAME",
            "SHAREPOINT_FOLDER_PATH",
        ]
        for key in keys:
            print(f"{key}={'SET' if os.getenv(key) else 'MISSING'}")

    if sources_config:
        sources = load_sources_config(sources_config)
    else:
        site_url = os.getenv("SHAREPOINT_SITE_URL", "").strip()
        if site_url:
            sources = [
                {
                    "source_id": "default",
                    "site_url": site_url,
                    "drive_name": os.getenv("SHAREPOINT_DRIVE_NAME", "Documents").strip()
                    or "Documents",
                    "folder_path": os.getenv("SHAREPOINT_FOLDER_PATH", "").strip(),
                    "source_dir": args.source or "",
                    "allowed_aad_groups": [],
                    "enabled": True,
                }
            ]
        else:
            sources = []

    if not sources:
        raise SystemExit("No SharePoint sources configured. Use --sources-config or SHAREPOINT_* env vars")

    policies = load_source_policies(Path(args.source_policies)) if args.source_policies else {}
    user_groups = [group.strip() for group in args.user_groups.split(",") if group.strip()]

    if args.print_allowed_sources:
        allowed = resolve_allowed_sources(sources, user_groups, policies if policies else None)
        for source_id in allowed:
            print(source_id)
        return

    if args.list_only:
        log_path = _resolve_log_path(args.sp_list_log)
        permissions_log_path = _resolve_log_path(args.sp_permissions_log)
        append_logs = False
        append_permissions_logs = False
        for source in sources:
            source_id = str(source.get("source_id", "")).strip() or "default"
            site_url = str(source.get("site_url", "")).strip()
            drive_name = str(source.get("drive_name", "Documents")).strip() or "Documents"
            folder_path_raw = str(source.get("folder_path", "")).strip()
            items = list_sharepoint_items(
                site_url=site_url,
                drive_name=drive_name,
                folder_path_raw=folder_path_raw,
            )
            for item in items:
                print(
                    f"[{source_id}] {item.get('name')} | {item.get('webUrl')} | "
                    f"{item.get('size', 0)} bytes"
                )
            if log_path:
                _write_sp_list_log(items, log_path, source_id=source_id, append=append_logs)
                append_logs = True

            if args.include_permissions and permissions_log_path:
                entries = get_sharepoint_item_permissions(
                    site_url=site_url,
                    drive_name=drive_name,
                    folder_path_raw=folder_path_raw,
                    max_items=args.permissions_max_items,
                    expand_group_members=args.expand_group_members,
                )
                _write_sp_permissions_log(
                    entries,
                    permissions_log_path,
                    source_id=source_id,
                    append=append_permissions_logs,
                )
                append_permissions_logs = True
        return

    persist_dir = Path(args.persist)
    extensions = [ext.strip().lower() for ext in args.extensions.split(",") if ext]

    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size must be > 0")
    if args.chunk_overlap < 0:
        raise SystemExit("--chunk-overlap must be >= 0")
    if args.chunk_overlap >= args.chunk_size:
        raise SystemExit("--chunk-overlap must be smaller than --chunk-size")

    log_path = _resolve_log_path(args.sp_list_log)
    permissions_log_path = _resolve_log_path(args.sp_permissions_log)
    skipped_log_path = _resolve_log_path(args.skipped_log)
    sync_state_path = Path(args.sync_state) if args.sync_state else (persist_dir / "sharepoint_sync_state.json")

    def _run_single_cycle() -> None:
        append_logs = False
        append_permissions_logs = False
        append_skipped_logs = False
        for source in sources:
            source_id = str(source.get("source_id", "")).strip() or "default"
            source_dir_value = str(source.get("source_dir", "")).strip() or args.source
            if not source_dir_value:
                raise RuntimeError(
                    f"Missing source_dir for source_id={source_id}. "
                    "Set source_dir in --sources-config or provide --source"
                )

            site_url = str(source.get("site_url", "")).strip()
            drive_name = str(source.get("drive_name", "Documents")).strip() or "Documents"
            folder_path_raw = str(source.get("folder_path", "")).strip()
            source_dir_path = Path(source_dir_value)

            if args.sync_files:
                sync_stats = sync_sharepoint_files_to_local(
                    site_url=site_url,
                    drive_name=drive_name,
                    folder_path_raw=folder_path_raw,
                    target_dir=source_dir_path,
                    max_items=args.sync_max_items,
                    overwrite=args.overwrite_local_files,
                    state_path=sync_state_path,
                    source_id=source_id,
                    use_delta=args.sync_use_delta,
                    reset_delta=args.sync_reset_delta,
                )
                print(
                    f"[{source_id}] sync listed={sync_stats['listed']} "
                    f"downloaded={sync_stats['downloaded']} "
                    f"skipped={sync_stats['skipped']} failed={sync_stats['failed']} "
                    f"deleted_local={sync_stats['deleted_local']} "
                    f"repaired_local={sync_stats.get('repaired_local', 0)}"
                )

            items = list_sharepoint_items(
                site_url=site_url,
                drive_name=drive_name,
                folder_path_raw=folder_path_raw,
            )
            if log_path:
                _write_sp_list_log(items, log_path, source_id=source_id, append=append_logs)
                append_logs = True

            if args.include_permissions and permissions_log_path:
                entries = get_sharepoint_item_permissions(
                    site_url=site_url,
                    drive_name=drive_name,
                    folder_path_raw=folder_path_raw,
                    max_items=args.permissions_max_items,
                    expand_group_members=args.expand_group_members,
                )
                _write_sp_permissions_log(
                    entries,
                    permissions_log_path,
                    source_id=source_id,
                    append=append_permissions_logs,
                )
                append_permissions_logs = True

            skipped_entries = ingest_sharepoint_docs(
                source_dir=source_dir_path,
                persist_dir=persist_dir,
                collection_name=args.collection,
                extensions=extensions,
                source_id=source_id,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )

            if skipped_log_path:
                _write_skipped_files_log(
                    skipped_entries,
                    skipped_log_path,
                    source_id=source_id,
                    append=append_skipped_logs,
                )
                append_skipped_logs = True

    if args.watch:
        while True:
            _run_single_cycle()
            time.sleep(args.interval)
    else:
        _run_single_cycle()


if __name__ == "__main__":
    main()
