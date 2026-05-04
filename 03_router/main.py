from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse

logger = logging.getLogger(__name__)

ROUTER_ROOT = Path(__file__).resolve().parent
APPS_CONFIG = ROUTER_ROOT / "apps.json"

app = FastAPI(title="Router", version="1.0.0")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/auth/login", include_in_schema=False)
async def auth_login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ai_framework/auth/login", status_code=307)


@app.post("/auth/login", include_in_schema=False)
async def auth_login_post_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ai_framework/auth/login", status_code=307)


@app.get("/auth/logout", include_in_schema=False)
async def auth_logout_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ai_framework/auth/logout", status_code=307)


@app.get("/auth/callback", include_in_schema=False)
async def auth_callback_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ai_framework/auth/callback", status_code=307)


def _load_apps() -> list[dict]:
    if not APPS_CONFIG.exists():
        return []
    text = APPS_CONFIG.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    return json.loads(text)


def _find_target(path: str) -> tuple[str, str, bool] | None:
    apps = _load_apps()
    for entry in apps:
        prefix = "/" + entry["path"].strip("/")
        if path == prefix or path.startswith(prefix + "/"):
            strip_prefix = bool(entry.get("strip_prefix", True))
            return entry["target"].rstrip("/"), prefix, strip_prefix
    return None


def _rewrite_location_header(location: str, target: str, prefix: str, strip_prefix: bool) -> str:
    if not location:
        return location

    split = urlsplit(location)

    # Internal absolute URL from upstream (e.g. http://localhost:8001/...) -> public relative path.
    if split.scheme and split.netloc and location.startswith(target):
        upstream_path = split.path or "/"
        if strip_prefix:
            public_path = prefix + (upstream_path if upstream_path.startswith("/") else f"/{upstream_path}")
        else:
            public_path = upstream_path
        return urlunsplit(("", "", public_path, split.query, split.fragment))

    # Relative upstream redirect when prefix is stripped: re-add the public app prefix.
    if location.startswith("/") and strip_prefix:
        if location == prefix or location.startswith(prefix + "/"):
            return location
        return prefix + location

    return location


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy(request: Request, full_path: str):
    path = "/" + full_path
    result = _find_target(path)

    if result is None:
        return Response(
            content=(
                "<h2>Router — Hranipex</h2>"
                "<p>Požadovaná aplikace nebyla nalezena.</p>"
                "<p>Zkontrolujte URL adresu.</p>"
            ),
            status_code=404,
            media_type="text/html",
        )

    target, prefix, strip_prefix = result
    stripped_path = path[len(prefix):] or "/"
    forward_path = stripped_path if strip_prefix else path
    target_url = target + forward_path
    if request.url.query:
        target_url += "?" + request.url.query

    headers = dict(request.headers)
    headers.pop("host", None)

    body = await request.body()

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
        )

    response_headers = dict(response.headers)
    response_headers.pop("transfer-encoding", None)

    if "location" in response_headers:
        response_headers["location"] = _rewrite_location_header(
            response_headers["location"],
            target,
            prefix,
            strip_prefix,
        )

    return StreamingResponse(
        content=iter([response.content]),
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type"),
    )