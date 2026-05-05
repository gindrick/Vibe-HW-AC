from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CurrentUser(BaseModel):
    user_id: str
    entra_object_id: str
    email: str
    display_name: str
    role: Literal["hm", "admin"] = "hm"


class MeResponse(BaseModel):
    user: CurrentUser


class PositionCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    description: str = Field(default="", max_length=16000)
    salary_from: float | None = None
    salary_to: float | None = None
    salary_visible: bool = False
    opened_at: datetime | None = None


class PositionDocumentSummary(BaseModel):
    document_id: str
    file_name: str
    document_type: str
    is_text: bool


class PositionResponse(BaseModel):
    position_id: str
    owner_id: str
    title: str
    description: str
    status: Literal["active", "archived"]
    salary_from: float | None = None
    salary_to: float | None = None
    salary_visible: bool = False
    opened_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    documents: list[PositionDocumentSummary] = []


class PositionsResponse(BaseModel):
    items: list[PositionResponse]


class CandidateCreateRequest(BaseModel):
    position_id: str
    full_name: str = Field(default="", max_length=250)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=64)
    external_ref: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=16000)


class CandidateUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=250)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=64)
    external_ref: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=16000)


class CandidateResponse(BaseModel):
    candidate_id: str
    position_id: str
    full_name: str
    email: str
    phone: str
    external_ref: str
    notes: str
    created_at: datetime
    updated_at: datetime


class CandidateListItem(BaseModel):
    candidate_id: str
    full_name: str
    email: str
    external_ref: str
    profile_status: str = "pending"
    profile_json: str | None = None
    evaluation_status: str | None = None
    recommendation: str | None = None
    overall_score: float | None = None
    evaluation_json: str | None = None
    is_stale: bool = False
    stale_reason: str | None = None


class PositionCandidatesResponse(BaseModel):
    items: list[CandidateListItem]


class CandidateDocumentSummary(BaseModel):
    document_id: str
    file_name: str
    document_type: str
    is_text: bool
    extracted_chars: int


class DocumentUploadResponse(BaseModel):
    document_id: str
    file_name: str
    mime_type: str
    is_processed: bool
    extracted_chars: int


class CandidateDashboardItem(BaseModel):
    candidate_id: str
    full_name: str
    email: str
    external_ref: str
    evaluation_status: str | None = None
    recommendation: str | None = None
    overall_score: float | None = None
    must_have_score: float | None = None
    card: dict | None = None
    is_stale: bool = False
    stale_reason: str | None = None


class DashboardStats(BaseModel):
    total: int
    recommended: int
    consider: int
    not_recommended: int
    pending: int


class BatchUploadItem(BaseModel):
    candidate_id: str
    file_name: str
    profile_status: str


class BatchUploadResponse(BaseModel):
    candidates: list[BatchUploadItem]


class PositionDashboardResponse(BaseModel):
    position_id: str
    title: str
    description: str
    status: str
    opened_at: datetime | None = None
    stats: DashboardStats
    candidates: list[CandidateDashboardItem]


