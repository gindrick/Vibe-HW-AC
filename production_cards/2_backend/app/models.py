from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

DB_SCHEMA = "production_cards"


class User(Base):
    __tablename__ = "Users"
    __table_args__ = {"schema": DB_SCHEMA}

    user_id: Mapped[str] = mapped_column("UserId", String(36), primary_key=True)
    entra_object_id: Mapped[str] = mapped_column("EntraObjectId", String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column("Email", String(320), index=True)
    display_name: Mapped[str] = mapped_column("DisplayName", String(200))
    role: Mapped[str] = mapped_column("Role", String(20), default="user")
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column("UpdatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Card(Base):
    __tablename__ = "Cards"
    __table_args__ = {"schema": DB_SCHEMA}

    card_id: Mapped[str] = mapped_column("CardId", String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column("OriginalFilename", String(500), default="")
    pdf_path: Mapped[str] = mapped_column("PdfPath", String(1000), default="")

    # Processing state: processing | ready | exported
    status: Mapped[str] = mapped_column("Status", String(20), default="processing", index=True)
    model_used: Mapped[str | None] = mapped_column("ModelUsed", String(100), nullable=True)

    # Card header
    title: Mapped[str | None] = mapped_column("Title", String(500), nullable=True)
    date: Mapped[str | None] = mapped_column("Datum", String(50), nullable=True)
    line_number: Mapped[str | None] = mapped_column("CisloLinky", String(50), nullable=True, index=True)
    shift: Mapped[str | None] = mapped_column("Smena", String(50), nullable=True)
    operator: Mapped[str | None] = mapped_column("Obsluha", String(100), nullable=True)

    # Product identification
    tool: Mapped[str | None] = mapped_column("Nastroj", String(100), nullable=True)
    produced_dimension: Mapped[str | None] = mapped_column("VyrabenyRozmer", String(100), nullable=True)
    surface_treatment: Mapped[str | None] = mapped_column("PovrchovaUprava", String(200), nullable=True)
    article_number: Mapped[str | None] = mapped_column("CisloArtiklu", String(200), nullable=True)
    material_granulate: Mapped[str | None] = mapped_column("MaterialGranulat", String(200), nullable=True)
    coating: Mapped[str | None] = mapped_column("Lakovani", String(200), nullable=True)

    # Measurements
    thickness: Mapped[str | None] = mapped_column("Tloustka", String(100), nullable=True)
    width: Mapped[str | None] = mapped_column("Sirka", String(100), nullable=True)
    u_profile: Mapped[str | None] = mapped_column("UProfil", String(50), nullable=True)
    surface: Mapped[str | None] = mapped_column("Povrch", String(50), nullable=True)
    gloss: Mapped[str | None] = mapped_column("Lesk", String(50), nullable=True)

    # Process parameters as JSON array: [{number, name, value}, ...]
    parameters_json: Mapped[str | None] = mapped_column("ParametryJson", Text, nullable=True)

    # Notes and footer
    notes: Mapped[str | None] = mapped_column("Poznamky", Text, nullable=True)
    footer_processed_by: Mapped[str | None] = mapped_column("FooterZpracoval", String(200), nullable=True)
    footer_approved_by: Mapped[str | None] = mapped_column("FooterSchvalil", String(200), nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DateTime, default=datetime.utcnow, index=True)
    created_by: Mapped[str] = mapped_column("CreatedBy", String(200), default="system")
    updated_at: Mapped[datetime] = mapped_column("UpdatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column("UpdatedBy", String(200), default="system")
