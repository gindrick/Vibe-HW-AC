from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "Users"
    __table_args__ = {"schema": "hr_eval"}

    user_id: Mapped[str] = mapped_column("UserId", String(36), primary_key=True)
    entra_object_id: Mapped[str] = mapped_column("EntraObjectId", String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column("Email", String(320), index=True)
    display_name: Mapped[str] = mapped_column("DisplayName", String(200))
    role: Mapped[str] = mapped_column("Role", String(20), default="hm")
    is_active: Mapped[bool] = mapped_column("IsActive", default=True)
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column("CreatedBy", String(200), default="system")
    updated_at: Mapped[datetime] = mapped_column("UpdatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column("UpdatedBy", String(200), default="system")

    positions: Mapped[list[Position]] = relationship("Position", back_populates="owner")


class Position(Base):
    __tablename__ = "Positions"
    __table_args__ = {"schema": "hr_eval"}

    position_id: Mapped[str] = mapped_column("PositionId", String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column("OwnerId", ForeignKey("hr_eval.Users.UserId"), index=True)
    title: Mapped[str] = mapped_column("Title", String(250))
    description: Mapped[str] = mapped_column("Description", Text, default="")
    status: Mapped[str] = mapped_column("Status", String(20), default="active", index=True)
    salary_from: Mapped[float | None] = mapped_column("SalaryFrom", Float, nullable=True)
    salary_to: Mapped[float | None] = mapped_column("SalaryTo", Float, nullable=True)
    salary_visible: Mapped[bool] = mapped_column("SalaryVisible", Boolean, default=False)
    opened_at: Mapped[datetime | None] = mapped_column("OpenedAt", DateTime, nullable=True)
    criteria_json: Mapped[str | None] = mapped_column("CriteriaJson", Text, nullable=True, default=None)
    criteria_hash: Mapped[str | None] = mapped_column("CriteriaHash", String(64), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column("CreatedBy", String(200), default="system")
    updated_at: Mapped[datetime] = mapped_column("UpdatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column("UpdatedBy", String(200), default="system")

    owner: Mapped[User] = relationship("User", back_populates="positions")
    documents: Mapped[list[PositionDocument]] = relationship("PositionDocument", back_populates="position", lazy="selectin")


class Candidate(Base):
    __tablename__ = "Candidates"
    __table_args__ = {"schema": "hr_eval"}

    candidate_id: Mapped[str] = mapped_column("CandidateId", String(36), primary_key=True)
    position_id: Mapped[str] = mapped_column("PositionId", ForeignKey("hr_eval.Positions.PositionId"), index=True)
    full_name: Mapped[str] = mapped_column("FullName", String(250))
    email: Mapped[str] = mapped_column("Email", String(320), default="")
    phone: Mapped[str] = mapped_column("Phone", String(64), default="")
    external_ref: Mapped[str] = mapped_column("ExternalRef", String(200), default="")
    notes: Mapped[str] = mapped_column("Notes", Text, default="")
    profile_json: Mapped[str | None] = mapped_column("ProfileJson", Text, nullable=True, default=None)
    profile_status: Mapped[str] = mapped_column("ProfileStatus", String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column("CreatedBy", String(200), default="system")
    updated_at: Mapped[datetime] = mapped_column("UpdatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column("UpdatedBy", String(200), default="system")


class Evaluation(Base):
    __tablename__ = "Evaluations"
    __table_args__ = {"schema": "hr_eval"}

    evaluation_id: Mapped[str] = mapped_column("EvaluationId", String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column("CandidateId", ForeignKey("hr_eval.Candidates.CandidateId"), unique=True, index=True)
    position_id: Mapped[str] = mapped_column("PositionId", ForeignKey("hr_eval.Positions.PositionId"), index=True)
    status: Mapped[str] = mapped_column("Status", String(20), default="pending", index=True)
    recommendation: Mapped[str] = mapped_column("Recommendation", String(20), default="")
    overall_score: Mapped[float] = mapped_column("OverallScore", default=0.0)
    must_have_score: Mapped[float] = mapped_column("MustHaveScore", default=0.0)
    evaluation_json: Mapped[str] = mapped_column("EvaluationJson", Text, default="")
    error_message: Mapped[str] = mapped_column("ErrorMessage", Text, default="")
    model_used: Mapped[str] = mapped_column("ModelUsed", String(120), default="")
    schema_version: Mapped[str] = mapped_column("SchemaVersion", String(20), default="1.0.0")
    is_stale: Mapped[bool] = mapped_column("IsStale", Boolean, server_default=false(), default=False)
    stale_reason: Mapped[str | None] = mapped_column("StaleReason", String(200), nullable=True, default=None)
    candidate_docs_hash: Mapped[str | None] = mapped_column("CandidateDocsHash", String(64), nullable=True, default=None)
    position_docs_hash: Mapped[str | None] = mapped_column("PositionDocsHash", String(64), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column("CreatedBy", String(200), default="system")
    updated_at: Mapped[datetime] = mapped_column("UpdatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column("UpdatedBy", String(200), default="system")


class PositionDocument(Base):
    __tablename__ = "PositionDocuments"
    __table_args__ = {"schema": "hr_eval"}

    document_id: Mapped[str] = mapped_column("DocumentId", String(36), primary_key=True)
    position_id: Mapped[str] = mapped_column("PositionId", ForeignKey("hr_eval.Positions.PositionId"), index=True)
    document_type: Mapped[str] = mapped_column("DocumentType", String(50), index=True)
    file_name: Mapped[str] = mapped_column("FileName", String(260))
    file_path: Mapped[str] = mapped_column("FilePath", String(1000))
    mime_type: Mapped[str] = mapped_column("MimeType", String(120), default="application/octet-stream")
    extracted_text: Mapped[str] = mapped_column("ExtractedText", Text, default="")
    is_processed: Mapped[bool] = mapped_column("IsProcessed", default=False)
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column("CreatedBy", String(200), default="system")
    updated_at: Mapped[datetime] = mapped_column("UpdatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column("UpdatedBy", String(200), default="system")

    position: Mapped[Position] = relationship("Position", back_populates="documents")


class CandidateDocument(Base):
    __tablename__ = "CandidateDocuments"
    __table_args__ = {"schema": "hr_eval"}

    document_id: Mapped[str] = mapped_column("DocumentId", String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column("CandidateId", ForeignKey("hr_eval.Candidates.CandidateId"), index=True)
    document_type: Mapped[str] = mapped_column("DocumentType", String(50), index=True)
    file_name: Mapped[str] = mapped_column("FileName", String(260))
    file_path: Mapped[str] = mapped_column("FilePath", String(1000))
    mime_type: Mapped[str] = mapped_column("MimeType", String(120), default="application/octet-stream")
    extracted_text: Mapped[str] = mapped_column("ExtractedText", Text, default="")
    content_hash: Mapped[str | None] = mapped_column("ContentHash", String(64), nullable=True, default=None)
    is_processed: Mapped[bool] = mapped_column("IsProcessed", default=False)
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column("CreatedBy", String(200), default="system")
    updated_at: Mapped[datetime] = mapped_column("UpdatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column("UpdatedBy", String(200), default="system")


