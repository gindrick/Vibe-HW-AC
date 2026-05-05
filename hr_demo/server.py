from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).resolve().parent
CANONICAL_INDEX_ROUTE = "static/index.html"
LOG_DIR = ROOT / "logs"
AUTH_LOG_PATH = LOG_DIR / "auth.log"


def _load_local_env(env_path: Path) -> None:
	if not env_path.exists():
		return
	for raw_line in env_path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip()
		value = value.strip().strip('"').strip("'")
		if key and key not in os.environ:
			os.environ[key] = value


_load_local_env(ROOT / ".env")

PUBLIC_PREFIX = os.getenv("DASHBOARD_PUBLIC_PREFIX", "/hr_demo").rstrip("/") or "/hr_demo"


def _setup_auth_logger() -> logging.Logger:
  LOG_DIR.mkdir(parents=True, exist_ok=True)
  logger = logging.getLogger("hr.auth")
  if logger.handlers:
    return logger

  logger.setLevel(logging.INFO)
  handler = RotatingFileHandler(AUTH_LOG_PATH, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
  handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
  logger.addHandler(handler)
  logger.propagate = False
  return logger


AUTH_LOGGER = _setup_auth_logger()

app = FastAPI(title="HR Static Server", version="1.1.0", root_path=PUBLIC_PREFIX)
app.add_middleware(
	SessionMiddleware,
	secret_key=os.getenv("SESSION_SECRET", "replace-this-dashboard-secret"),
	same_site="lax",
)


def _auth_provider() -> str:
	return os.getenv("AUTH_PROVIDER", "none").strip().lower()


def _is_ldap_enabled() -> bool:
	if _auth_provider() != "ldap":
		return False
	return bool(os.getenv("LDAP_SERVER") and os.getenv("LDAP_DOMAIN"))


def _is_auth_enabled() -> bool:
	return _is_ldap_enabled()


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
		from ldap3 import Connection, SIMPLE, Server

		server = Server(ldap_server)
		conn = Connection(server, user=principal, password=password, authentication=SIMPLE)
		ok = conn.bind()
		if ok:
			conn.unbind()
		return ok
	except Exception:
		return False


def _require_user(request: Request) -> Optional[dict]:
	if not _is_auth_enabled():
		return None
	user = request.session.get("user")
	if not user:
		raise HTTPException(status_code=401, detail="Authentication required")
	return user


def _client_ip(request: Request) -> str:
  x_forwarded_for = request.headers.get("x-forwarded-for", "").strip()
  if x_forwarded_for:
    return x_forwarded_for.split(",")[0].strip()
  if request.client and request.client.host:
    return request.client.host
  return "unknown"


def _content_cipher_key() -> str:
  return os.getenv("DASHBOARD_CONTENT_KEY", "").strip()


def _decrypt_encrypted_html(file_path: Path) -> str:
  key = _content_cipher_key()
  if not key:
    raise HTTPException(status_code=500, detail="Missing DASHBOARD_CONTENT_KEY")

  try:
    from cryptography.fernet import Fernet, InvalidToken
  except Exception as exc:
    raise HTTPException(status_code=500, detail="Missing cryptography dependency") from exc

  try:
    token = file_path.read_bytes()
    cipher = Fernet(key.encode("utf-8"))
    html_bytes = cipher.decrypt(token)
    return html_bytes.decode("utf-8")
  except InvalidToken as exc:
    raise HTTPException(status_code=500, detail="Dashboard decryption failed") from exc


def _login_page(error: Optional[str] = None) -> str:
	error_html = (
		f'<div class="error-box"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><span>{error}</span></div>'
		if error
		else ""
	)
	return f"""
<!doctype html>
<html lang=\"cs\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Přihlášení — Hranipex</title>
  <link rel=\"icon\" type=\"image/svg+xml\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23111827'/%3E%3Cpath d='M14 20h36v4H14zM14 30h36v4H14zM14 40h22v4H14z' fill='%2338bdf8'/%3E%3C/svg%3E\" />
  <link href=\"https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap\" rel=\"stylesheet\">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'DM Sans', system-ui, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }}
    .wrap {{
      width: 100%;
      max-width: 420px;
      animation: fadeUp 0.35s ease both;
    }}
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(16px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    .card {{
      background: #111827;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 20px;
      padding: 2.5rem 2.5rem 2rem;
      box-shadow: 0 24px 60px rgba(0,0,0,0.5);
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      margin-bottom: 2rem;
    }}
    .brand-dot {{
      width: 10px; height: 10px;
      border-radius: 50%;
      background: #38bdf8;
    }}
    .brand-name {{
      font-size: 13px;
      font-weight: 600;
      color: rgba(255,255,255,0.5);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    h1 {{
      font-family: 'DM Serif Display', serif;
      font-size: 1.9rem;
      font-weight: 400;
      line-height: 1.2;
      color: #f8fafc;
      margin-bottom: 0.4rem;
    }}
    h1 em {{ font-style: italic; color: rgba(248,250,252,0.45); }}
    .subtitle {{
      font-size: 13px;
      color: rgba(255,255,255,0.35);
      margin-bottom: 2rem;
    }}
    .error-box {{
      display: flex;
      align-items: flex-start;
      gap: 0.6rem;
      margin-bottom: 1.25rem;
      padding: 0.85rem 1rem;
      background: rgba(239,68,68,0.12);
      border: 1px solid rgba(239,68,68,0.3);
      border-radius: 10px;
      color: #fca5a5;
      font-size: 13px;
      line-height: 1.5;
    }}
    label {{
      display: block;
      font-size: 12px;
      font-weight: 500;
      color: rgba(255,255,255,0.45);
      text-transform: uppercase;
      letter-spacing: 0.07em;
      margin-bottom: 0.5rem;
    }}
    input {{
      width: 100%;
      padding: 0.75rem 1rem;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(255,255,255,0.04);
      color: #f1f5f9;
      font-family: 'DM Sans', sans-serif;
      font-size: 14px;
      margin-bottom: 1.1rem;
      transition: border-color 0.15s, background 0.15s;
      outline: none;
    }}
    input:focus {{
      border-color: rgba(56,189,248,0.5);
      background: rgba(56,189,248,0.05);
    }}
    input::placeholder {{ color: rgba(255,255,255,0.2); }}
    .btn {{
      width: 100%;
      padding: 0.85rem 1rem;
      border-radius: 10px;
      border: 0;
      background: #38bdf8;
      color: #082f49;
      font-family: 'DM Sans', sans-serif;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.15s, transform 0.1s;
      margin-top: 0.25rem;
    }}
    .btn:hover {{ background: #7dd3fc; }}
    .btn:active {{ transform: scale(0.98); }}
    .footer {{
      text-align: center;
      margin-top: 1.5rem;
      font-size: 12px;
      color: rgba(255,255,255,0.2);
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <div class=\"brand\">
        <div class=\"brand-dot\"></div>
        <span class=\"brand-name\">Hranipex &middot; HR Portal</span>
      </div>
      <h1>Vítejte <em>zpět</em></h1>
      <p class=\"subtitle\">Přihlaste se firemním účtem pro přístup k dashboardu.</p>
      {error_html}
      <form method=\"post\" action=\"{PUBLIC_PREFIX}/auth/login\">
        <label>Uživatelské jméno</label>
        <input name=\"username\" type=\"text\" placeholder=\"jmeno.prijmeni\" required autocomplete=\"username\" autofocus />
        <label>Heslo</label>
        <input name=\"password\" type=\"password\" placeholder=\"••••••••\" required autocomplete=\"current-password\" />
        <button type=\"submit\" class=\"btn\">Přihlásit se →</button>
      </form>
    </div>
    <p class=\"footer\">Přístup pouze pro oprávněné zaměstnance.</p>
  </div>
</body>
</html>
"""


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
	return Response(status_code=204)


@app.get("/auth/login")
def auth_login(request: Request):
    if not _is_auth_enabled():
        return RedirectResponse(url=f"{PUBLIC_PREFIX}/static/index.html", status_code=302)
    if request.session.get("user"):
        return RedirectResponse(url=f"{PUBLIC_PREFIX}/static/index.html", status_code=302)
    error_message = request.query_params.get("error")
    return HTMLResponse(_login_page(error_message))


@app.post("/auth/login")
def auth_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
  client_ip = _client_ip(request)
  if not _is_ldap_enabled():
    AUTH_LOGGER.warning("LOGIN_SKIPPED user=%s ip=%s reason=ldap_disabled", username.strip(), client_ip)
    return RedirectResponse(url=f"{PUBLIC_PREFIX}/auth/login", status_code=302)
  if not _ldap_bind_user(username, password):
    AUTH_LOGGER.info("LOGIN_FAILED user=%s ip=%s", username.strip(), client_ip)
    return HTMLResponse(_login_page("Neplatné přihlašovací údaje nebo nepovolený uživatel."), status_code=401)

  normalized = _normalize_ldap_user(username)
  domain = os.getenv("LDAP_DOMAIN", "").strip().lower()
  email = normalized if "@" in normalized else f"{normalized}@{domain}"
  request.session["user"] = {
    "name": username.strip(),
    "email": email,
    "auth_provider": "ldap",
  }
  AUTH_LOGGER.info("LOGIN_SUCCESS user=%s email=%s ip=%s", username.strip(), email, client_ip)
  return RedirectResponse(url=f"{PUBLIC_PREFIX}/static/index.html", status_code=302)


@app.get("/auth/logout")
def auth_logout(request: Request):
	request.session.clear()
	return RedirectResponse(url=f"{PUBLIC_PREFIX}/auth/login", status_code=302)


@app.get("/api/me")
def api_me(request: Request):
	if not _is_auth_enabled():
		return {"authenticated": False, "auth_enabled": False, "auth_provider": _auth_provider(), "user": None}
	user = request.session.get("user")
	return {"authenticated": bool(user), "auth_enabled": True, "auth_provider": _auth_provider(), "user": user}


@app.get("/")
def root(request: Request):
  return RedirectResponse(url=f"{PUBLIC_PREFIX}/static/index.html", status_code=302)


@app.get("/{file_path:path}")
def serve_file(file_path: str, request: Request):
  if _is_auth_enabled() and not request.session.get("user"):
    return RedirectResponse(url=f"{PUBLIC_PREFIX}/auth/login", status_code=302)

  clean = file_path.strip("/")
  if not clean:
    clean = CANONICAL_INDEX_ROUTE

  candidate = (ROOT / clean).resolve()
  if not str(candidate).startswith(str(ROOT.resolve())):
    raise HTTPException(status_code=400, detail="Invalid path")

  if candidate.is_dir():
    candidate = candidate / "index.html"

  # If encrypted dashboard exists, serve it instead of plaintext index.html.
  if clean == CANONICAL_INDEX_ROUTE:
    encrypted_candidate = (ROOT / "static" / "index.html2").resolve()
    if str(encrypted_candidate).startswith(str(ROOT.resolve())) and encrypted_candidate.exists():
      candidate = encrypted_candidate

  if not candidate.exists() or not candidate.is_file():
    raise HTTPException(status_code=404, detail="Not Found")

  if candidate.suffix == ".html2":
    html = _decrypt_encrypted_html(candidate)
    return HTMLResponse(content=html)

  return FileResponse(candidate)
