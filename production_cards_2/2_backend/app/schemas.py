from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class CurrentUser(BaseModel):
    user_id: str
    entra_object_id: str
    email: str
    display_name: str
    role: str = "user"


class MeResponse(BaseModel):
    user: CurrentUser


class Parameter(BaseModel):
    number: int | None = None
    name: str = ""
    value: str = ""
    unit: str = ""


class CardUpdateRequest(BaseModel):
    title: str | None = None
    date: str | None = None
    line_number: str | None = None
    shift: str | None = None
    operator: str | None = None
    tool: str | None = None
    produced_dimension: str | None = None
    surface_treatment: str | None = None
    article_number: str | None = None
    material_granulate: str | None = None
    coating: str | None = None
    thickness: str | None = None
    width: str | None = None
    u_profile: str | None = None
    surface: str | None = None
    gloss: str | None = None
    parameters: list[Parameter] | None = None
    notes: str | None = None
    footer_processed_by: str | None = None
    footer_approved_by: str | None = None


class CardResponse(BaseModel):
    card_id: str
    original_filename: str
    status: str
    model_used: str | None
    title: str | None
    date: str | None
    line_number: str | None
    shift: str | None
    operator: str | None
    tool: str | None
    produced_dimension: str | None
    surface_treatment: str | None
    article_number: str | None
    material_granulate: str | None
    coating: str | None
    thickness: str | None
    width: str | None
    u_profile: str | None
    surface: str | None
    gloss: str | None
    parameters: list[Parameter]
    notes: str | None
    footer_processed_by: str | None
    footer_approved_by: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class CardListItem(BaseModel):
    card_id: str
    original_filename: str
    status: str
    line_number: str | None
    date: str | None
    shift: str | None
    operator: str | None
    tool: str | None
    produced_dimension: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str


class CardListResponse(BaseModel):
    items: list[CardListItem]
    total: int
    page: int
    page_size: int


class UploadResponse(BaseModel):
    card_id: str
    status: str
    message: str
