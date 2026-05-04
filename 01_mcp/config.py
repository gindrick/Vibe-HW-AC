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


ROOT = Path(__file__).resolve().parent
_load_dotenv(ROOT / ".env")
_load_dotenv(ROOT.parent / ".env")


@dataclass(frozen=True)
class Settings:
    mssql_host: str
    mssql_port: int
    mssql_db: str
    mssql_user: str
    mssql_password: str
    mssql_driver: str

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
)
