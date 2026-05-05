from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException, Request, status

from app.config import settings
from app.models import User
from app.schemas import CurrentUser


@dataclass
class IdentityClaims:
    entra_object_id: str
    email: str
    display_name: str
    role: str


def _claims_from_request(request: Request) -> IdentityClaims:
    if settings.dev_auth_bypass and settings.env != "prod":
        return IdentityClaims(
            entra_object_id="dev-bypass-user",
            email=settings.dev_auth_user_email,
            display_name=settings.dev_auth_user_name,
            role="user",
        )

    if settings.auth_mode == "ldap":
        session_user = request.session.get("user")
        if not session_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        return IdentityClaims(
            entra_object_id=session_user["email"],
            email=session_user["email"],
            display_name=session_user.get("name", session_user["email"]),
            role=session_user.get("role", "user"),
        )

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported auth mode")


def get_or_create_user(db, request: Request) -> CurrentUser:
    from sqlalchemy.orm import Session
    claims = _claims_from_request(request)
    user = db.query(User).filter(User.entra_object_id == claims.entra_object_id).first()

    if user is None:
        user = User(
            user_id=str(uuid4()),
            entra_object_id=claims.entra_object_id,
            email=claims.email,
            display_name=claims.display_name,
            role=claims.role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email = claims.email
        user.display_name = claims.display_name
        db.commit()
        db.refresh(user)

    return CurrentUser(
        user_id=user.user_id,
        entra_object_id=user.entra_object_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )
