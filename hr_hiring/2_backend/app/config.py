from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


ROOT = Path(__file__).resolve().parents[1]
_load_dotenv(ROOT / ".env")
_load_dotenv(ROOT.parent / ".env")


def _split_csv(raw: str, fallback: str) -> list[str]:
    source = raw.strip() if raw else fallback
    return [item.strip() for item in source.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    env: str
    log_level: str
    auth_mode: str
    dev_auth_bypass: bool
    dev_auth_user_email: str
    dev_auth_user_name: str
    entra_tenant_id: str
    entra_client_id: str
    entra_audience: str
    entra_jwks_url: str
    mssql_host: str
    mssql_port: int
    mssql_db: str
    mssql_user: str
    mssql_password: str
    mssql_driver: str
    upload_root: str
    session_secret: str
    ldap_server: str
    ldap_domain: str
    ldap_allowed_users: str
    frontend_url: str
    public_api_prefix: str
    test_mode: bool
    mcp_mode: str
    mcp_server_url: str
    litellm_base_url: str
    litellm_api_key: str
    litellm_model: str
    backend_host: str
    backend_port: int
    cors_origins: list[str]
    auto_create_schema: bool

    @property
    def sqlalchemy_url(self) -> str:
        driver = quote_plus(self.mssql_driver)
        return (
            f"mssql+pyodbc://{self.mssql_user}:{quote_plus(self.mssql_password)}"
            f"@{self.mssql_host}:{self.mssql_port}/{self.mssql_db}"
            f"?driver={driver}&TrustServerCertificate=yes"
        )


settings = Settings(
    env=os.getenv("ENV", "dev"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    auth_mode=os.getenv("AUTH_MODE", "entra").lower(),
    dev_auth_bypass=os.getenv("DEV_AUTH_BYPASS", "true").lower() == "true",
    dev_auth_user_email=os.getenv("DEV_AUTH_USER_EMAIL", "hm@example.com"),
    dev_auth_user_name=os.getenv("DEV_AUTH_USER_NAME", "Demo Hiring Manager"),
    entra_tenant_id=os.getenv("ENTRA_TENANT_ID", ""),
    entra_client_id=os.getenv("ENTRA_CLIENT_ID", ""),
    entra_audience=os.getenv("ENTRA_AUDIENCE", ""),
    entra_jwks_url=os.getenv("ENTRA_JWKS_URL", ""),
    mssql_host=os.getenv("MSSQL_HOST", "localhost"),
    mssql_port=int(os.getenv("MSSQL_PORT", "1433")),
    mssql_db=os.getenv("MSSQL_DB", "hr_eval"),
    mssql_user=os.getenv("MSSQL_USER", "sa"),
    mssql_password=os.getenv("MSSQL_PASSWORD", ""),
    mssql_driver=os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server"),
    upload_root=os.getenv("UPLOAD_ROOT", "./storage/uploads"),
    session_secret=os.getenv("SESSION_SECRET", "hr-hiring-change-this-secret-key"),
    ldap_server=os.getenv("LDAP_SERVER", ""),
    ldap_domain=os.getenv("LDAP_DOMAIN", ""),
    ldap_allowed_users=os.getenv("LDAP_ALLOWED_USERS", ""),
    frontend_url=os.getenv("FRONTEND_URL", "http://192.168.41.43:5173/hr_hiring/"),
    public_api_prefix=os.getenv("PUBLIC_API_PREFIX", "").rstrip("/"),
    test_mode=os.getenv("TEST_MODE", "false").lower() == "true",
    mcp_mode=os.getenv("MCP_MODE", "local").lower(),
    mcp_server_url=os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8002/mcp"),
    litellm_base_url=os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000"),
    litellm_api_key=os.getenv("LITELLM_API_KEY", "sk-local"),
    litellm_model=os.getenv("LITELLM_MODEL", "llm-default"),
    backend_host=os.getenv("BACKEND_HOST", "127.0.0.1"),
    backend_port=int(os.getenv("BACKEND_PORT", "8010")),
    cors_origins=_split_csv(
        os.getenv("BACKEND_CORS_ORIGINS", ""),
        "http://127.0.0.1:5173,http://localhost:5173,http://localhost:8000",
    ),
    auto_create_schema=os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true",
)
