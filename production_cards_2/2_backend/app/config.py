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
_load_dotenv(ROOT.parent.parent / ".env")


def _split_csv(raw: str, fallback: str) -> list[str]:
    source = raw.strip() if raw else fallback
    return [item.strip() for item in source.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    env: str
    auth_mode: str
    dev_auth_bypass: bool
    dev_auth_user_email: str
    dev_auth_user_name: str
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
    extraction_pipeline: str  # "litellm" (default) or "agent"
    agent_model: str          # litellm model_name pro agent pipeline (supervisor + sub-agents)
    litellm_base_url: str
    litellm_api_key: str
    litellm_model: str
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
    auth_mode=os.getenv("AUTH_MODE", "ldap").lower(),
    dev_auth_bypass=os.getenv("DEV_AUTH_BYPASS", "true").lower() == "true",
    dev_auth_user_email=os.getenv("DEV_AUTH_USER_EMAIL", "dev@hranipex.local"),
    dev_auth_user_name=os.getenv("DEV_AUTH_USER_NAME", "Dev User"),
    mssql_host=os.getenv("MSSQL_HOST", "localhost"),
    mssql_port=int(os.getenv("MSSQL_PORT", "1433")),
    mssql_db=os.getenv("MSSQL_DB", "production_cards"),
    mssql_user=os.getenv("MSSQL_USER", "sa"),
    mssql_password=os.getenv("MSSQL_PASSWORD", ""),
    mssql_driver=os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server"),
    upload_root=os.getenv("UPLOAD_ROOT", "./storage/uploads"),
    session_secret=os.getenv("SESSION_SECRET", "production-cards-2-change-this-secret"),
    ldap_server=os.getenv("LDAP_SERVER", ""),
    ldap_domain=os.getenv("LDAP_DOMAIN", ""),
    ldap_allowed_users=os.getenv("LDAP_ALLOWED_USERS", ""),
    frontend_url=os.getenv("FRONTEND_URL", "http://127.0.0.1:5175/production_cards_2/"),
    public_api_prefix=os.getenv("PUBLIC_API_PREFIX", "").rstrip("/"),
    extraction_pipeline=os.getenv("EXTRACTION_PIPELINE", "litellm"),
    agent_model=os.getenv("AGENT_MODEL", "anthropic-claude-sonnet-4"),
    litellm_base_url=os.getenv("LITELLM_BASE_URL", "http://localhost:4000"),
    litellm_api_key=os.getenv("LITELLM_API_KEY", "dummy"),
    litellm_model=os.getenv("LITELLM_MODEL", "gpt-4o-mini"),
    cors_origins=_split_csv(
        os.getenv("BACKEND_CORS_ORIGINS", ""),
        "http://127.0.0.1:5175,http://localhost:5175",
    ),
    auto_create_schema=os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true",
)
