from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from config import settings

engine = create_engine(settings.sqlalchemy_url, future=True, pool_pre_ping=True)


@contextmanager
def get_connection() -> Iterator[Connection]:
    with engine.begin() as conn:
        yield conn
