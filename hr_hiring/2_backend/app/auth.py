from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.schemas import CurrentUser


@dataclass
class IdentityClaims:
    entra_object_id: str
    email: str
    display_name: str
    role: str


def _bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth_header.split(" ", 1)[1].strip()


def _decode_token_without_validation(token: str) -> dict[str, Any]:
    try:
        return jwt.get_unverified_claims(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT") from exc


def _resolve_claim(payload: dict[str, Any], keys: list[str], default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _validate_signature_if_configured(token: str) -> dict[str, Any]:
    if not settings.entra_jwks_url or not settings.entra_audience:
        return _decode_token_without_validation(token)

    try:
        jwks = httpx.get(settings.entra_jwks_url, timeout=10.0).json()
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        if not kid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token kid")

        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key_data:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signing key not found")

        issuer = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
        return jwt.decode(
            token,
            key_data,
            algorithms=["RS256"],
            audience=settings.entra_audience,
            issuer=issuer,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token validation failed") from exc


def _claims_from_token(request: Request) -> IdentityClaims:
    if settings.dev_auth_bypass and settings.env != "prod":
        return IdentityClaims(
            entra_object_id="dev-bypass-user",
            email=settings.dev_auth_user_email,
            display_name=settings.dev_auth_user_name,
            role="hm",
        )

    if settings.auth_mode == "ldap":
        session_user = request.session.get("user")
        if not session_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        return IdentityClaims(
            entra_object_id=session_user["email"],
            email=session_user["email"],
            display_name=session_user.get("name", session_user["email"]),
            role=session_user.get("role", "hm"),
        )

    if settings.auth_mode != "entra":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported auth mode")

    token = _bearer_token(request)
    payload = _validate_signature_if_configured(token)

    oid = _resolve_claim(payload, ["oid", "sub"])
    email = _resolve_claim(payload, ["preferred_username", "email", "upn"])
    display_name = _resolve_claim(payload, ["name"], default=email)
    role = "admin" if "admin" in [r.lower() for r in payload.get("roles", []) if isinstance(r, str)] else "hm"

    if not oid or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Required claims missing")

    return IdentityClaims(
        entra_object_id=oid,
        email=email,
        display_name=display_name,
        role=role,
    )


def get_or_create_user(db: Session, request: Request) -> CurrentUser:
    claims = _claims_from_token(request)
    user = db.query(User).filter(User.entra_object_id == claims.entra_object_id).first()

    if user is None:
        user = User(
            user_id=str(uuid4()),
            entra_object_id=claims.entra_object_id,
            email=claims.email,
            display_name=claims.display_name,
            role=claims.role,
            created_by=claims.email,
            updated_by=claims.email,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Keep profile synced with Entra attributes.
        user.email = claims.email
        user.display_name = claims.display_name
        user.role = claims.role
        user.updated_by = claims.email
        db.commit()
        db.refresh(user)

    return CurrentUser(
        user_id=user.user_id,
        entra_object_id=user.entra_object_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )
