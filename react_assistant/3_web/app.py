from __future__ import annotations

import os
import sys
import json
import importlib
import logging
import secrets
from pathlib import Path
from typing import Any, Literal, Optional
from collections import defaultdict
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi import Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Response
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
import msal
import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AI_FRAMEWORK_PATH = PROJECT_ROOT / "2_ai_framework"
WEB_ROOT = Path(__file__).resolve().parent
if str(AI_FRAMEWORK_PATH) not in sys.path:
    sys.path.insert(0, str(AI_FRAMEWORK_PATH))

load_dotenv(WEB_ROOT / ".env", override=True)
load_dotenv(AI_FRAMEWORK_PATH / ".env", override=False)

logger = logging.getLogger(__name__)

app = FastAPI(title="Agent Web UI", version="0.1.0", root_path="/react_assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "replace-this-session-secret"),
    same_site="lax",
)

STATIC_DIR = WEB_ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
IMG_DIR = WEB_ROOT / "img"
if IMG_DIR.exists():
    app.mount("/img", StaticFiles(directory=IMG_DIR), name="img")


class AskRequest(BaseModel):
    query: str = Field(..., min_length=2)
    response_mode: Literal["short", "detailed", "citations"] = "short"
    user_message: str = '{"user_id":"web_user"}'
    persist_dir: Optional[str] = None
    collection_name: Optional[str] = None
    n_results: int = Field(default=5, ge=1, le=12)


class AskResponse(BaseModel):
    success: bool
    answer: str
    error: Optional[str] = None
    reasoning: Optional[str] = None


def _auth_provider() -> str:
    return os.getenv("AUTH_PROVIDER", "none").strip().lower()


def _is_entra_enabled() -> bool:
    if _auth_provider() != "entra":
        return False
    required = [
        os.getenv("ENTRA_TENANT_ID"),
        os.getenv("ENTRA_CLIENT_ID"),
        os.getenv("ENTRA_CLIENT_SECRET"),
    ]
    return all(required)


def _is_ldap_enabled() -> bool:
    if _auth_provider() != "ldap":
        return False
    return bool(os.getenv("LDAP_SERVER") and os.getenv("LDAP_DOMAIN"))


def _is_auth_enabled() -> bool:
    return _is_entra_enabled() or _is_ldap_enabled()


def _entra_authority() -> str:
    tenant_id = os.getenv("ENTRA_TENANT_ID", "")
    return f"https://login.microsoftonline.com/{tenant_id}"


def _entra_scopes() -> list[str]:
    raw = os.getenv("ENTRA_SCOPES", "User.Read")
    reserved = {"openid", "profile", "offline_access"}
    scopes = [scope.strip() for scope in raw.split() if scope.strip() and scope.strip() not in reserved]
    return scopes or ["User.Read"]


def _entra_redirect_uri(request: Request) -> str:
    configured = os.getenv("ENTRA_REDIRECT_URI")
    if configured:
        return configured
    return str(request.url_for("auth_callback"))


def _msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        client_id=os.getenv("ENTRA_CLIENT_ID", ""),
        authority=_entra_authority(),
        client_credential=os.getenv("ENTRA_CLIENT_SECRET", ""),
    )


def _allowed_domains() -> list[str]:
    raw = os.getenv("ENTRA_ALLOWED_DOMAINS", "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _ldap_allowed_users() -> set[str]:
    raw = os.getenv("LDAP_ALLOWED_USERS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _normalize_ldap_user(username: str) -> str:
    return username.strip().lower()


def _is_ldap_user_allowed(username: str) -> bool:
    allowed = _ldap_allowed_users()
    if not allowed:
        return True
    normalized = _normalize_ldap_user(username)
    if normalized in allowed:
        return True
    if "@" not in normalized:
        domain = os.getenv("LDAP_DOMAIN", "").strip().lower()
        return f"{normalized}@{domain}" in allowed
    return False


def _ldap_login_page(error: Optional[str] = None) -> str:
    error_html = (
        f'<div style="margin-bottom:12px;padding:10px;border-radius:8px;background:#7f1d1d;color:#fecaca;">{error}</div>'
        if error
        else ""
    )
    return f"""
<!doctype html>
<html lang=\"cs\">
    <head>
        <meta charset=\"UTF-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
        <title>Přihlášení</title>
    </head>
    <body style=\"font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center;\">
                <form method=\"post\" action=\"/react_assistant/auth/login\" style=\"width:100%;max-width:380px;background:#111827;border:1px solid #334155;padding:20px;border-radius:12px;box-sizing:border-box;\">
            <h1 style=\"margin:0 0 14px;font-size:22px;\">Přihlášení</h1>
            {error_html}
            <label style=\"display:block;margin-bottom:6px;\">Uživatelské jméno</label>
                        <input name=\"username\" type=\"text\" required style=\"width:100%;padding:10px;border-radius:8px;border:1px solid #475569;background:#0b1220;color:#e2e8f0;margin-bottom:12px;box-sizing:border-box;outline:none;\" />
            <label style=\"display:block;margin-bottom:6px;\">Heslo</label>
                        <input name=\"password\" type=\"password\" required style=\"width:100%;padding:10px;border-radius:8px;border:1px solid #475569;background:#0b1220;color:#e2e8f0;margin-bottom:14px;box-sizing:border-box;outline:none;\" />
                        <button type=\"submit\" style=\"width:100%;padding:10px;border-radius:8px;border:0;background:#38bdf8;color:#082f49;font-weight:700;cursor:pointer;box-sizing:border-box;\">Přihlásit</button>
        </form>
    </body>
</html>
"""


def _ldap_bind_user(username: str, password: str) -> bool:
    if not username.strip() or not password:
        return False
    if not _is_ldap_user_allowed(username):
        return False

    ldap_server = os.getenv("LDAP_SERVER", "").strip()
    ldap_domain = os.getenv("LDAP_DOMAIN", "").strip()
    if not ldap_server or not ldap_domain:
        return False

    principal = username.strip()
    if "@" not in principal:
        principal = f"{principal}@{ldap_domain}"

    try:
        from ldap3 import Connection, Server, SIMPLE

        server = Server(ldap_server)
        conn = Connection(server, user=principal, password=password, authentication=SIMPLE)
        ok = conn.bind()
        if ok:
            conn.unbind()
        return ok
    except Exception:
        logger.exception("LDAP bind failed")
        return False


def _ldap_resolve_user_email(username: str, password: str) -> str:
    ldap_server = os.getenv("LDAP_SERVER", "").strip()
    ldap_domain = os.getenv("LDAP_DOMAIN", "").strip()
    if not ldap_server or not ldap_domain:
        return ""

    principal = username.strip()
    if "@" not in principal:
        principal = f"{principal}@{ldap_domain}"

    username_local = principal.split("@", 1)[0]

    try:
        from ldap3 import ALL, Connection, SIMPLE, SUBTREE, Server

        server = Server(ldap_server, get_info=ALL)
        conn = Connection(server, user=principal, password=password, authentication=SIMPLE)
        if not conn.bind():
            return ""

        try:
            info = getattr(server, "info", None)
            info_other = getattr(info, "other", {}) if info is not None else {}
            base_candidates = []
            for key in ("defaultNamingContext", "namingContexts"):
                values = info_other.get(key, []) if isinstance(info_other, dict) else []
                for value in values:
                    base = str(value).strip()
                    if base and base not in base_candidates:
                        base_candidates.append(base)

            if not base_candidates:
                domain_parts = [part.strip() for part in ldap_domain.split(".") if part.strip()]
                if domain_parts:
                    base_candidates.append(",".join(f"DC={part}" for part in domain_parts))

            search_filters = [
                f"(&(objectClass=user)(userPrincipalName={principal}))",
                f"(&(objectClass=user)(sAMAccountName={username_local}))",
            ]

            for search_base in base_candidates:
                for search_filter in search_filters:
                    found = conn.search(
                        search_base=search_base,
                        search_filter=search_filter,
                        search_scope=SUBTREE,
                        attributes=["mail", "userPrincipalName"],
                        size_limit=1,
                    )
                    if not found or not conn.entries:
                        continue

                    entry = conn.entries[0]
                    mail = str(getattr(entry, "mail", "") or "").strip()
                    upn = str(getattr(entry, "userPrincipalName", "") or "").strip()
                    resolved = (mail or upn).lower()
                    if resolved and "@" in resolved:
                        return resolved

            return ""
        finally:
            conn.unbind()
    except Exception:
        logger.exception("LDAP email resolve failed")
        return ""


def _require_user(request: Request) -> Optional[dict]:
    if not _is_auth_enabled():
        return None
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _default_persist_dir() -> str:
    return str((AI_FRAMEWORK_PATH / ".sharepoint_chroma_test").resolve()).replace("\\", "/")


def _default_collection() -> str:
    return os.getenv("CHROMA_COLLECTION", "sharepoint_docs_test")


def _load_source_dir_map() -> dict[str, Path]:
    default_config = AI_FRAMEWORK_PATH / "src" / "pipelines" / "sharepoint_sources.json"
    configured = os.getenv("SHAREPOINT_SOURCES_CONFIG", str(default_config))
    config_path = Path(configured)
    if not config_path.is_absolute():
        config_path = (AI_FRAMEWORK_PATH / config_path).resolve()

    if not config_path.exists():
        return {}

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(data, list):
        return {}

    mapping: dict[str, Path] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id", "default")).strip() or "default"
        source_dir_value = str(item.get("source_dir", "")).strip()
        if not source_dir_value:
            continue

        source_dir_path = Path(source_dir_value)
        if not source_dir_path.is_absolute():
            source_dir_path = (AI_FRAMEWORK_PATH / source_dir_path).resolve()
        else:
            source_dir_path = source_dir_path.resolve()

        mapping[source_id] = source_dir_path
    return mapping


def _extract_sharepoint_url(metadata: dict[str, Any]) -> Optional[str]:
    keys = (
        "sharepoint_url",
        "sharepoint_web_url",
        "web_url",
        "webUrl",
        "source_url",
        "document_url",
    )
    for key in keys:
        value = str(metadata.get(key, "")).strip()
        if value.startswith("https://") or value.startswith("http://"):
            return value
    return None


def _load_source_web_url_map(persist_path: Path) -> dict[tuple[str, str], str]:
    sync_state_path = persist_path / "sharepoint_sync_state.json"
    if not sync_state_path.exists():
        return {}

    try:
        raw = json.loads(sync_state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    mapping: dict[tuple[str, str], str] = {}
    for source_id, source_state in raw.items():
        if not isinstance(source_state, dict):
            continue

        clean_source_id = str(source_id).strip()
        if not clean_source_id:
            continue

        item_index = source_state.get("item_index", {})
        if not isinstance(item_index, dict):
            continue

        for item in item_index.values():
            if not isinstance(item, dict):
                continue

            file_name = str(item.get("name", "")).strip()
            if not file_name:
                continue

            url = ""
            for key in ("sharepoint_url", "web_url", "webUrl"):
                value = str(item.get(key, "")).strip()
                if value.startswith("https://") or value.startswith("http://"):
                    url = value
                    break

            if url:
                mapping[(clean_source_id, file_name)] = url

    return mapping


def _get_collection_sources(persist_dir: str, collection_name: str) -> list[dict]:
    persist_path = Path(persist_dir).resolve()
    if not persist_path.exists():
        return []

    max_scan = int(os.getenv("CHROMA_SOURCES_MAX_SCAN", "5000"))
    client = chromadb.PersistentClient(path=str(persist_path))
    collection = client.get_or_create_collection(name=collection_name)
    total = max(0, int(collection.count()))
    if total == 0:
        return []

    fetch_limit = min(total, max(1, max_scan))
    data = collection.get(include=["metadatas"], limit=fetch_limit)
    metadatas = data.get("metadatas", []) if isinstance(data, dict) else []

    grouped: dict[tuple[str, str], int] = defaultdict(int)
    grouped_urls: dict[tuple[str, str], str] = {}
    for item in metadatas:
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("file_name", "")).strip()
        source_id = str(item.get("source_id", "")).strip()
        if not file_name:
            continue
        key = (source_id, file_name)
        grouped[key] += 1

        if key not in grouped_urls:
            sharepoint_url = _extract_sharepoint_url(item)
            if sharepoint_url:
                grouped_urls[key] = sharepoint_url

    source_dir_map = _load_source_dir_map()
    source_web_url_map = _load_source_web_url_map(persist_path)

    rows = []
    for (source_id, file_name), chunks in grouped.items():
        file_url = grouped_urls.get((source_id, file_name)) or source_web_url_map.get((source_id, file_name))
        if not file_url:
            source_dir = source_dir_map.get(source_id)
            if source_dir:
                candidate = (source_dir / file_name).resolve()
                if str(candidate).startswith(str(source_dir)) and candidate.exists() and candidate.is_file():
                    source_id_q = quote(source_id, safe="")
                    file_name_q = quote(file_name, safe="")
                    file_url = f"/api/source-file?source_id={source_id_q}&file_name={file_name_q}"

        rows.append(
            {
                "source_id": source_id,
                "file_name": file_name,
                "chunks": chunks,
                "file_url": file_url,
            }
        )

    rows.sort(key=lambda item: (item.get("source_id", ""), item.get("file_name", "")))
    return rows


@app.get("/api/source-file")
def get_source_file(request: Request, source_id: str, file_name: str):
    _require_user(request)

    clean_source_id = (source_id or "").strip()
    clean_file_name = (file_name or "").strip()
    if not clean_source_id or not clean_file_name:
        raise HTTPException(status_code=400, detail="source_id and file_name are required")

    if Path(clean_file_name).name != clean_file_name:
        raise HTTPException(status_code=400, detail="Invalid file_name")

    source_dir_map = _load_source_dir_map()
    source_dir = source_dir_map.get(clean_source_id)
    if not source_dir:
        raise HTTPException(status_code=404, detail="Unknown source_id")

    candidate = (source_dir / clean_file_name).resolve()
    if not str(candidate).startswith(str(source_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(candidate)


def _build_task(payload: AskRequest) -> str:
    persist_dir = payload.persist_dir or _default_persist_dir()
    collection_name = payload.collection_name or _default_collection()
    return (
        "Answer the user's question using chroma_query tool.\n\n"
        "Steps:\n"
        "1. Call chroma_query with:\n"
        f"   - query='{payload.query}'\n"
        f"   - user_message='{payload.user_message}'\n"
        f"   - persist_dir='{persist_dir}'\n"
        f"   - collection_name='{collection_name}'\n"
        f"   - n_results={payload.n_results}\n"
        "2. Synthesize a direct answer to the user's question from retrieved content.\n"
        "3. Do not describe internal tools or process unless asked.\n"
        "4. If evidence is weak or missing, clearly say what is uncertain.\n"
        "5. Respond in the same language as the user's question.\n"
        f"6. Use response_mode='{payload.response_mode}' where allowed values are short|detailed|citations."
    )


def _create_agent():
    agents_module = importlib.import_module("src.agents")
    react_agent_class = getattr(agents_module, "ReActAgent")
    return react_agent_class(
        name="Web ReAct Agent",
        model=os.getenv("AGENT_MODEL", "oai-gpt-4.1-nano"),
    )


@app.get("/")
def index(request: Request):
    if _is_auth_enabled() and not request.session.get("user"):
        return RedirectResponse(url="/react_assistant/auth/login", status_code=302)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/auth/login")
def auth_login(request: Request):

    if not _is_auth_enabled():
        return RedirectResponse(url="/react_assistant", status_code=302)


    if _is_ldap_enabled():
        error_message = request.query_params.get("error")
        return HTMLResponse(_ldap_login_page(error_message))


    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    request.session["oauth_next"] = "/react_assistant"

    auth_url = _msal_app().get_authorization_request_url(
        scopes=_entra_scopes(),
        state=state,
        redirect_uri=_entra_redirect_uri(request),
        prompt="select_account",
    )
    return RedirectResponse(url=auth_url, status_code=302)


@app.post("/auth/login")
def auth_login_post(request: Request, username: str = Form(...), password: str = Form(...)):

    if not _is_ldap_enabled():
        return RedirectResponse(url="/react_assistant/auth/login", status_code=302)


    if not _ldap_bind_user(username, password):
        return HTMLResponse(_ldap_login_page("Neplatné přihlašovací údaje."), status_code=401)

    normalized = _normalize_ldap_user(username)
    domain = os.getenv("LDAP_DOMAIN", "").strip().lower()
    fallback_email = normalized if "@" in normalized else f"{normalized}@{domain}"
    resolved_email = _ldap_resolve_user_email(username, password)
    email = resolved_email or fallback_email
    request.session["user"] = {
        "name": username.strip(),
        "email": email,
        "oid": None,
        "auth_provider": "ldap",
    }
    return RedirectResponse(url="/react_assistant", status_code=302)


@app.get("/auth/callback", name="auth_callback")
def auth_callback(request: Request):

    if not _is_entra_enabled():
        return RedirectResponse(url="/react_assistant", status_code=302)


    if request.query_params.get("error"):
        error_description = request.query_params.get("error_description", "Authentication failed")
        raise HTTPException(status_code=401, detail=error_description)

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    expected_state = request.session.get("oauth_state")
    if not code or not state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth callback state")

    token_result = _msal_app().acquire_token_by_authorization_code(
        code=code,
        scopes=_entra_scopes(),
        redirect_uri=_entra_redirect_uri(request),
    )
    if "error" in token_result:
        raise HTTPException(
            status_code=401,
            detail=token_result.get("error_description") or token_result.get("error") or "Authentication failed",
        )

    claims = token_result.get("id_token_claims") or {}
    email = (claims.get("email") or claims.get("preferred_username") or "").lower()
    domains = _allowed_domains()
    if domains and ("@" not in email or email.split("@")[-1] not in domains):
        raise HTTPException(status_code=403, detail="User domain is not allowed")

    request.session["user"] = {
        "name": claims.get("name") or email or "User",
        "email": email,
        "oid": claims.get("oid"),
    }
    request.session.pop("oauth_state", None)
    next_url = request.session.pop("oauth_next", "/react_assistant")
    return RedirectResponse(url=next_url, status_code=302)


@app.get("/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/react_assistant", status_code=302)


@app.get("/api/me")
def api_me(request: Request):
    if not _is_auth_enabled():
        return {"authenticated": False, "auth_enabled": False, "auth_provider": _auth_provider(), "user": None}
    user = request.session.get("user")
    return {"authenticated": bool(user), "auth_enabled": True, "auth_provider": _auth_provider(), "user": user}


@app.get("/api/config")
def get_config(request: Request) -> dict:
    user = _require_user(request)
    return {
        "agent_model": os.getenv("AGENT_MODEL", "oai-gpt-4.1-nano"),
        "persist_dir": _default_persist_dir(),
        "collection_name": _default_collection(),
        "litellm_base_url": os.getenv("LITELLM_BASE_URL", "http://localhost:4000"),
        "mcp_server_url": os.getenv("MCP_SERVER_URL", "http://localhost:8002"),
        "auth_enabled": _is_auth_enabled(),
        "auth_provider": _auth_provider(),
        "user": user,
    }


@app.get("/api/sources")
def get_sources(request: Request) -> dict:
    _require_user(request)
    persist_dir = _default_persist_dir()
    collection_name = _default_collection()
    try:
        sources = _get_collection_sources(persist_dir=persist_dir, collection_name=collection_name)
        return {
            "persist_dir": persist_dir,
            "collection_name": collection_name,
            "count": len(sources),
            "sources": sources,
        }
    except Exception as exc:
        logger.exception("Failed to list Chroma sources")
        return {
            "persist_dir": persist_dir,
            "collection_name": collection_name,
            "count": 0,
            "sources": [],
            "error": str(exc),
        }


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: Request, payload: AskRequest) -> AskResponse:
    _require_user(request)
    task = _build_task(payload)
    agent = _create_agent()
    agent.max_iterations = int(os.getenv("AGENT_MAX_ITERATIONS", "4"))

    try:
        result = await agent.execute(task)
        if not result.success:
            return AskResponse(success=False, answer="", error=result.error, reasoning=result.reasoning)
        return AskResponse(success=True, answer=str(result.result), reasoning=result.reasoning)
    except Exception as exc:
        logger.exception("Unhandled /api/ask error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            await agent.disconnect()
        except Exception:
            pass


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request, exc: Exception):
    logger.exception("Unhandled server exception")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "answer": "",
            "error": str(exc) or "Internal Server Error",
            "reasoning": None,
        },
    )
