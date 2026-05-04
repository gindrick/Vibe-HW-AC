import logging
import logging.handlers
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth_ldap, cards, me


def _configure_logging() -> None:
    log_dir = Path(__file__).resolve().parents[1] / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
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

    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Dedicated costs log — plain file, UTF-8, never rotated
    costs_fh = logging.FileHandler(
        log_dir / "costs.log",
        mode="a",
        encoding="utf-8",
    )
    costs_fh.setFormatter(logging.Formatter("%(message)s"))
    costs_fh.setLevel(logging.INFO)
    costs_logger = logging.getLogger("production_cards_2.costs")
    costs_logger.setLevel(logging.INFO)
    costs_logger.addHandler(costs_fh)
    costs_logger.propagate = False


_configure_logging()

app = FastAPI(title="Production Cards 2 Backend", version="0.1.0")

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


def _ensure_db_schema() -> None:
    from sqlalchemy import text
    statements = [
        "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'production_cards_2') EXEC('CREATE SCHEMA production_cards_2')",
    ]
    try:
        with engine.connect() as conn:
            for sql in statements:
                conn.execute(text(sql))
            conn.commit()
    except Exception:
        pass


@app.on_event("startup")
def on_startup() -> None:
    Path(settings.upload_root).mkdir(parents=True, exist_ok=True)
    if settings.auto_create_schema:
        _ensure_db_schema()
        Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "production-cards-2-backend", "env": settings.env}


app.include_router(auth_ldap.router)
app.include_router(me.router)
app.include_router(cards.router)
