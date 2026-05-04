from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.schemas import CurrentUser, MeResponse

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=MeResponse)
def me(current_user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=current_user)
