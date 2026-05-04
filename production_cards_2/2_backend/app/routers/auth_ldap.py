from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import ROOT, settings

router = APIRouter(prefix="/auth", tags=["auth"])

_AUTH_LOG_PATH = ROOT / "logs" / "auth.log"


def _setup_auth_logger() -> logging.Logger:
    (ROOT / "logs").mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("production_cards.auth")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(_AUTH_LOG_PATH, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


AUTH_LOGGER = _setup_auth_logger()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _ldap_allowed_users() -> set[str]:
    raw = settings.ldap_allowed_users
    return {u.strip().lower() for u in raw.split(",") if u.strip()}


def _is_user_allowed(username: str) -> bool:
    allowed = _ldap_allowed_users()
    if not allowed:
        return True
    norm = username.strip().lower()
    if norm in allowed:
        return True
    if "@" not in norm and settings.ldap_domain:
        return f"{norm}@{settings.ldap_domain.lower()}" in allowed
    return False


def _ldap_bind(username: str, password: str) -> bool:
    if not username.strip() or not password:
        return False
    if not _is_user_allowed(username):
        return False
    if not settings.ldap_server or not settings.ldap_domain:
        return False

    principal = username.strip()
    if "@" not in principal:
        principal = f"{principal}@{settings.ldap_domain}"

    try:
        from ldap3 import SIMPLE, Connection, Server
        server = Server(settings.ldap_server)
        conn = Connection(server, user=principal, password=password, authentication=SIMPLE)
        ok = conn.bind()
        if ok:
            conn.unbind()
        return ok
    except Exception:
        return False


def _login_page(error: Optional[str] = None) -> str:
    error_html = (
        f'<div class="error-box">'
        f'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px">'
        f'<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>'
        f'</svg><span>{error}</span></div>'
        if error else ""
    )
    return f"""<!doctype html>
<html lang="cs">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Přihlášení — Výrobní karty</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23111827'/%3E%3Cpath d='M14 20h36v4H14zM14 30h36v4H14zM14 40h22v4H14z' fill='%2338bdf8'/%3E%3C/svg%3E" />
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'DM Sans', system-ui, sans-serif;
      background: #0f172a; color: #e2e8f0;
      min-height: 100vh; display: flex;
      align-items: center; justify-content: center; padding: 1.5rem;
    }}
    .wrap {{ width: 100%; max-width: 420px; animation: fadeUp 0.35s ease both; }}
    @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(16px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    .card {{
      background: #111827; border: 1px solid rgba(255,255,255,0.08);
      border-radius: 20px; padding: 2.5rem 2.5rem 2rem;
      box-shadow: 0 24px 60px rgba(0,0,0,0.5);
    }}
    .brand {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 2rem; }}
    .brand-dot {{ width: 10px; height: 10px; border-radius: 50%; background: #38bdf8; }}
    .brand-name {{ font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.5); letter-spacing: 0.06em; text-transform: uppercase; }}
    h1 {{ font-family: 'DM Serif Display', serif; font-size: 1.9rem; font-weight: 400; line-height: 1.2; color: #f8fafc; margin-bottom: 0.4rem; }}
    h1 em {{ font-style: italic; color: rgba(248,250,252,0.45); }}
    .subtitle {{ font-size: 13px; color: rgba(255,255,255,0.35); margin-bottom: 2rem; }}
    .error-box {{
      display: flex; align-items: flex-start; gap: 0.6rem; margin-bottom: 1.25rem;
      padding: 0.85rem 1rem; background: rgba(239,68,68,0.12);
      border: 1px solid rgba(239,68,68,0.3); border-radius: 10px;
      color: #fca5a5; font-size: 13px; line-height: 1.5;
    }}
    label {{ display: block; font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.45); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 0.5rem; }}
    input {{
      width: 100%; padding: 0.75rem 1rem; border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04);
      color: #f1f5f9; font-family: 'DM Sans', sans-serif; font-size: 14px;
      margin-bottom: 1.1rem; transition: border-color 0.15s, background 0.15s; outline: none;
    }}
    input:focus {{ border-color: rgba(56,189,248,0.5); background: rgba(56,189,248,0.05); }}
    input::placeholder {{ color: rgba(255,255,255,0.2); }}
    .btn {{
      width: 100%; padding: 0.85rem 1rem; border-radius: 10px; border: 0;
      background: #38bdf8; color: #082f49; font-family: 'DM Sans', sans-serif;
      font-size: 14px; font-weight: 700; cursor: pointer; transition: background 0.15s, transform 0.1s; margin-top: 0.25rem;
    }}
    .btn:hover {{ background: #7dd3fc; }}
    .btn:active {{ transform: scale(0.98); }}
    .footer {{ text-align: center; margin-top: 1.5rem; font-size: 12px; color: rgba(255,255,255,0.2); }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="brand"><div class="brand-dot"></div><span class="brand-name">Hranipex &middot; Výrobní karty</span></div>
      <h1>Vítejte <em>zpět</em></h1>
      <p class="subtitle">Přihlaste se firemním účtem pro přístup k aplikaci.</p>
      {error_html}
      <form method="post" action="{settings.public_api_prefix}/auth/login">
        <label>Uživatelské jméno</label>
        <input name="username" type="text" placeholder="jmeno.prijmeni" required autocomplete="username" autofocus />
        <label>Heslo</label>
        <input name="password" type="password" placeholder="••••••••" required autocomplete="current-password" />
        <button type="submit" class="btn">Přihlásit se →</button>
      </form>
    </div>
    <p class="footer">Přístup pouze pro oprávněné zaměstnance.</p>
  </div>
</body>
</html>"""


@router.get("/login", include_in_schema=False)
def get_login(request: Request):
    if settings.auth_mode != "ldap":
        return RedirectResponse(url=settings.frontend_url, status_code=302)
    if request.session.get("user"):
        return RedirectResponse(url=settings.frontend_url, status_code=302)
    error = request.query_params.get("error")
    return HTMLResponse(_login_page(error))


@router.post("/login", include_in_schema=False)
def post_login(request: Request, username: str = Form(...), password: str = Form(...)):
    ip = _client_ip(request)
    if settings.auth_mode != "ldap":
        AUTH_LOGGER.warning("LOGIN_SKIPPED user=%s ip=%s", username.strip(), ip)
        return RedirectResponse(url=settings.frontend_url, status_code=302)

    if not _ldap_bind(username, password):
        AUTH_LOGGER.info("LOGIN_FAILED user=%s ip=%s", username.strip(), ip)
        return HTMLResponse(_login_page("Neplatné přihlašovací údaje nebo nepovolený uživatel."), status_code=401)

    norm = username.strip().lower()
    email = norm if "@" in norm else f"{norm}@{settings.ldap_domain.lower()}"
    request.session["user"] = {"name": username.strip(), "email": email, "auth_provider": "ldap"}
    AUTH_LOGGER.info("LOGIN_SUCCESS user=%s email=%s ip=%s", username.strip(), email, ip)
    return RedirectResponse(url=settings.frontend_url, status_code=302)


@router.get("/logout", include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=f"{settings.public_api_prefix}/auth/login", status_code=302)


@router.get("/status")
def auth_status(request: Request) -> dict:
    if settings.dev_auth_bypass and settings.env != "prod":
        user = {"name": settings.dev_auth_user_name, "email": settings.dev_auth_user_email}
        return {"authenticated": True, "auth_mode": "dev", "user": user}
    user = request.session.get("user")
    return {"authenticated": bool(user), "auth_mode": settings.auth_mode, "user": user}
