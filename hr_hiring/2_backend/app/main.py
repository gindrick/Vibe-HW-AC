import logging
import logging.handlers

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth_ldap, candidates, evaluations, llm_stats, me, positions


def _configure_logging() -> None:
    log_dir = Path(__file__).resolve().parents[1] / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — 10 MB per file, keep 5
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "backend.out.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    root.addHandler(sh)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access", "langgraph"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Dedicated costs log — plain file, never rotated, UTF-8
    costs_fh = logging.FileHandler(
        log_dir / "costs.log",
        mode="a",
        encoding="utf-8",
    )
    costs_fh.setFormatter(logging.Formatter("%(message)s"))
    costs_fh.setLevel(logging.INFO)
    costs_logger = logging.getLogger("costs")
    costs_logger.setLevel(logging.INFO)
    costs_logger.addHandler(costs_fh)
    costs_logger.propagate = False  # don't duplicate to root/backend.out.log


_configure_logging()

app = FastAPI(title="HR Hiring Backend", version="0.2.0")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _migrate_criteria_cache_columns() -> None:
    """Add criteria cache columns to Positions if they don't exist yet."""
    from sqlalchemy import text

    statements = [
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Positions' AND COLUMN_NAME='CriteriaJson') ALTER TABLE hr_eval.Positions ADD CriteriaJson NVARCHAR(MAX) NULL",
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Positions' AND COLUMN_NAME='CriteriaHash') ALTER TABLE hr_eval.Positions ADD CriteriaHash NVARCHAR(64) NULL",
    ]
    try:
        with engine.connect() as conn:
            for sql in statements:
                conn.execute(text(sql))
            conn.commit()
    except Exception:
        pass


def _migrate_evaluation_staleness_columns() -> None:
    """Add staleness-tracking columns to Evaluations if they don't exist yet."""
    from sqlalchemy import text

    statements = [
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Evaluations' AND COLUMN_NAME='IsStale') ALTER TABLE hr_eval.Evaluations ADD IsStale BIT NOT NULL DEFAULT 0",
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Evaluations' AND COLUMN_NAME='StaleReason') ALTER TABLE hr_eval.Evaluations ADD StaleReason NVARCHAR(200) NULL",
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Evaluations' AND COLUMN_NAME='CandidateDocsHash') ALTER TABLE hr_eval.Evaluations ADD CandidateDocsHash NVARCHAR(64) NULL",
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Evaluations' AND COLUMN_NAME='PositionDocsHash') ALTER TABLE hr_eval.Evaluations ADD PositionDocsHash NVARCHAR(64) NULL",
    ]
    try:
        with engine.connect() as conn:
            for sql in statements:
                conn.execute(text(sql))
            conn.commit()
    except Exception:
        pass


def _migrate_candidate_columns() -> None:
    """Add new columns to Candidates/CandidateDocuments if they don't exist yet."""
    from sqlalchemy import text

    statements = [
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Candidates' AND COLUMN_NAME='ProfileJson') ALTER TABLE hr_eval.Candidates ADD ProfileJson NVARCHAR(MAX) NULL",
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Candidates' AND COLUMN_NAME='ProfileStatus') ALTER TABLE hr_eval.Candidates ADD ProfileStatus VARCHAR(20) NOT NULL DEFAULT 'pending'",
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='CandidateDocuments' AND COLUMN_NAME='ContentHash') ALTER TABLE hr_eval.CandidateDocuments ADD ContentHash VARCHAR(64) NULL",
    ]
    try:
        with engine.connect() as conn:
            for sql in statements:
                conn.execute(text(sql))
            conn.commit()
    except Exception:
        pass


def _migrate_position_columns() -> None:
    """Add new columns to Positions if they don't exist yet (MSSQL compatible)."""
    from sqlalchemy import text

    statements = [
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Positions' AND COLUMN_NAME='SalaryFrom') ALTER TABLE hr_eval.Positions ADD SalaryFrom FLOAT NULL",
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Positions' AND COLUMN_NAME='SalaryTo') ALTER TABLE hr_eval.Positions ADD SalaryTo FLOAT NULL",
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Positions' AND COLUMN_NAME='SalaryVisible') ALTER TABLE hr_eval.Positions ADD SalaryVisible BIT NOT NULL DEFAULT 0",
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='hr_eval' AND TABLE_NAME='Positions' AND COLUMN_NAME='OpenedAt') ALTER TABLE hr_eval.Positions ADD OpenedAt DATETIME NULL",
    ]
    try:
        with engine.connect() as conn:
            for sql in statements:
                conn.execute(text(sql))
            conn.commit()
    except Exception:
        pass  # Table may not exist yet — create_all handles that


@app.on_event("startup")
def on_startup() -> None:
    Path(settings.upload_root).mkdir(parents=True, exist_ok=True)
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
        _migrate_position_columns()
        _migrate_criteria_cache_columns()
        _migrate_candidate_columns()
        _migrate_evaluation_staleness_columns()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "hr-hiring-backend",
        "env": settings.env,
        "auth_mode": settings.auth_mode,
    }


app.include_router(auth_ldap.router)
app.include_router(me.router)
app.include_router(positions.router)
app.include_router(candidates.router)
app.include_router(evaluations.router)
app.include_router(llm_stats.router)

