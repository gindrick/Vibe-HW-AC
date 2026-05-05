from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth import get_or_create_user
from app.database import SessionLocal
from app.schemas import CurrentUser


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    return get_or_create_user(db=db, request=request)
