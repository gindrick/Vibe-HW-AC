from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
_BACKEND_ROOT = _ROOT.parent / "2_backend"

# Load .env from backend first, then root, then local override
load_dotenv(_BACKEND_ROOT / ".env", override=False)
load_dotenv(_ROOT.parent.parent / ".env", override=False)
load_dotenv(_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    mssql_host: str
    mssql_port: int
    mssql_db: str
    mssql_user: str
    mssql_password: str
    mssql_driver: str
    litellm_base_url: str
    litellm_api_key: str
    litellm_model: str
    backend_url: str

    @property
    def sqlalchemy_url(self) -> str:
        driver = quote_plus(self.mssql_driver)
        return (
            f"mssql+pyodbc://{self.mssql_user}:{quote_plus(self.mssql_password)}"
            f"@{self.mssql_host}:{self.mssql_port}/{self.mssql_db}"
            f"?driver={driver}&TrustServerCertificate=yes"
        )


settings = Settings(
    mssql_host=os.getenv("MSSQL_HOST", "localhost"),
    mssql_port=int(os.getenv("MSSQL_PORT", "1433")),
    mssql_db=os.getenv("MSSQL_DB", "hr_eval"),
    mssql_user=os.getenv("MSSQL_USER", "sa"),
    mssql_password=os.getenv("MSSQL_PASSWORD", ""),
    mssql_driver=os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server"),
    litellm_base_url=os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000"),
    litellm_api_key=os.getenv("LITELLM_API_KEY", "sk-local"),
    litellm_model=os.getenv("LITELLM_MODEL", "llm-default"),
    backend_url=os.getenv("BACKEND_URL", "http://127.0.0.1:8010"),
)
