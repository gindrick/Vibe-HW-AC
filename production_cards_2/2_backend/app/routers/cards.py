from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user, get_db
from app.models import Card
from app.schemas import (
    CardListItem, CardListResponse, CardResponse, CardUpdateRequest,
    CurrentUser, Parameter, UploadResponse,
)
from app.services import pdf_renderer, xlsx_exporter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cards", tags=["cards"])


async def _run_extractor(pdf_path: str) -> dict:
    if settings.extraction_pipeline == "agent":
        from app.services.agent_pipeline import extract_card_data
        return await extract_card_data(pdf_path)
    from app.services.llm_extractor import extract_card_data
    return await asyncio.to_thread(extract_card_data, pdf_path)

UPLOAD_ROOT = Path(settings.upload_root)


def _parse_parameter(p: dict) -> Parameter:
    return Parameter(
        number=p.get("number") if p.get("number") is not None else p.get("cislo"),
        name=p.get("name") or p.get("nazev") or "",
        value=p.get("value") or p.get("hodnota") or "",
        unit=p.get("unit") or "",
    )


def _card_to_response(card: Card) -> CardResponse:
    try:
        params_raw = json.loads(card.parameters_json or "[]")
        parametry = [_parse_parameter(p) for p in params_raw]
    except Exception:
        parametry = []

    return CardResponse(
        card_id=card.card_id,
        original_filename=card.original_filename,
        status=card.status,
        model_used=card.model_used,
        title=card.title,
        date=card.date,
        line_number=card.line_number,
        shift=card.shift,
        operator=card.operator,
        tool=card.tool,
        produced_dimension=card.produced_dimension,
        surface_treatment=card.surface_treatment,
        article_number=card.article_number,
        material_granulate=card.material_granulate,
        coating=card.coating,
        thickness=card.thickness,
        width=card.width,
        u_profile=card.u_profile,
        surface=card.surface,
        gloss=card.gloss,
        parameters=parametry,
        notes=card.notes,
        footer_processed_by=card.footer_processed_by,
        footer_approved_by=card.footer_approved_by,
        created_at=card.created_at,
        updated_at=card.updated_at,
        created_by=card.created_by,
        updated_by=card.updated_by,
    )


async def _process_card(card_id: str, pdf_path: str) -> None:
    """Background task: extract card data and update DB."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        card = db.query(Card).filter(Card.card_id == card_id).first()
        if card is None:
            return

        data = await _run_extractor(pdf_path)

        card.title = data.get("title")
        card.date = data.get("date")
        card.line_number = data.get("line_number")
        card.shift = data.get("shift")
        card.operator = data.get("operator")
        card.tool = data.get("tool")
        card.produced_dimension = data.get("produced_dimension")
        card.surface_treatment = data.get("surface_treatment")
        card.article_number = data.get("article_number")
        card.material_granulate = data.get("material_granulate")
        card.coating = data.get("coating")
        card.thickness = data.get("thickness")
        card.width = data.get("width")
        card.u_profile = data.get("u_profile")
        card.surface = data.get("surface")
        card.gloss = data.get("gloss")
        card.parameters_json = json.dumps(data.get("parameters") or [], ensure_ascii=False)
        card.notes = data.get("notes")
        card.footer_processed_by = data.get("footer_processed_by")
        card.footer_approved_by = data.get("footer_approved_by")
        card.model_used = data.get("model_used")
        card.status = "ready"
        card.updated_at = datetime.utcnow()
        db.commit()
        logger.info("Card %s processed, model=%s", card_id, card.model_used)
    except Exception as exc:
        logger.error("Card %s processing failed: %s", card_id, exc)
        try:
            card = db.query(Card).filter(Card.card_id == card_id).first()
            if card:
                card.status = "error"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_card(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Pouze PDF soubory jsou povoleny.")

    card_id = str(uuid4())
    safe_name = file.filename.replace("\\", "_").replace("/", "_").strip()

    dest_dir = UPLOAD_ROOT / card_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = dest_dir / safe_name
    content = await file.read()
    pdf_path.write_bytes(content)

    now = datetime.utcnow()
    card = Card(
        card_id=card_id,
        original_filename=safe_name,
        pdf_path=str(pdf_path),
        status="processing",
        created_at=now,
        updated_at=now,
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(card)
    db.commit()

    background_tasks.add_task(_process_card, card_id, str(pdf_path))

    return UploadResponse(
        card_id=card_id,
        status="processing",
        message="PDF bylo nahráno, probíhá extrakce dat.",
    )


@router.get("", response_model=CardListResponse)
def list_cards(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    status: str | None = Query(None),
    line_number: str | None = Query(None),
    date: str | None = Query(None),
    operator: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CardListResponse:
    q = db.query(Card)

    if status:
        q = q.filter(Card.status == status)
    if line_number:
        q = q.filter(Card.line_number.ilike(f"%{line_number}%"))
    if date:
        q = q.filter(Card.date.ilike(f"%{date}%"))
    if operator:
        q = q.filter(Card.operator.ilike(f"%{operator}%"))
    if search:
        like = f"%{search}%"
        q = q.filter(
            Card.original_filename.ilike(like) |
            Card.line_number.ilike(like) |
            Card.operator.ilike(like) |
            Card.tool.ilike(like)
        )

    total = q.with_entities(func.count(Card.card_id)).scalar()

    sortable = {
        "created_at": Card.created_at,
        "updated_at": Card.updated_at,
        "date": Card.date,
        "line_number": Card.line_number,
        "status": Card.status,
    }
    col = sortable.get(sort_by, Card.created_at)
    q = q.order_by(desc(col) if sort_dir == "desc" else asc(col))
    cards = q.offset((page - 1) * page_size).limit(page_size).all()

    return CardListResponse(
        items=[
            CardListItem(
                card_id=c.card_id,
                original_filename=c.original_filename,
                status=c.status,
                line_number=c.line_number,
                date=c.date,
                shift=c.shift,
                operator=c.operator,
                tool=c.tool,
                produced_dimension=c.produced_dimension,
                created_at=c.created_at,
                updated_at=c.updated_at,
                created_by=c.created_by,
            )
            for c in cards
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{card_id}", response_model=CardResponse)
def get_card(
    card_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CardResponse:
    card = db.query(Card).filter(Card.card_id == card_id).first()
    if card is None:
        raise HTTPException(status_code=404, detail="Karta nenalezena.")
    return _card_to_response(card)


@router.get("/{card_id}/pdf-page/{page_number}")
def get_pdf_page(
    card_id: str,
    page_number: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    card = db.query(Card).filter(Card.card_id == card_id).first()
    if card is None:
        raise HTTPException(status_code=404, detail="Karta nenalezena.")
    try:
        png_b64 = pdf_renderer.render_page_as_png_b64(card.pdf_path, page_number=page_number)
        page_count = pdf_renderer.get_page_count(card.pdf_path)
        return {"page_b64": png_b64, "page_number": page_number, "page_count": page_count}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/{card_id}", response_model=CardResponse)
def update_card(
    card_id: str,
    payload: CardUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CardResponse:
    card = db.query(Card).filter(Card.card_id == card_id).first()
    if card is None:
        raise HTTPException(status_code=404, detail="Karta nenalezena.")

    for field in [
        "title", "date", "line_number", "shift", "operator",
        "tool", "produced_dimension", "surface_treatment", "article_number",
        "material_granulate", "coating", "thickness", "width",
        "u_profile", "surface", "gloss", "notes",
        "footer_processed_by", "footer_approved_by",
    ]:
        val = getattr(payload, field)
        if val is not None:
            setattr(card, field, val)

    if payload.parameters is not None:
        card.parameters_json = json.dumps(
            [p.model_dump() for p in payload.parameters], ensure_ascii=False
        )

    card.updated_at = datetime.utcnow()
    card.updated_by = current_user.email
    db.commit()
    db.refresh(card)
    return _card_to_response(card)


@router.get("/{card_id}/export")
def export_card(
    card_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    card = db.query(Card).filter(Card.card_id == card_id).first()
    if card is None:
        raise HTTPException(status_code=404, detail="Karta nenalezena.")

    params_raw = json.loads(card.parameters_json or "[]")
    card_dict = {
        "title": card.title, "date": card.date, "line_number": card.line_number,
        "shift": card.shift, "operator": card.operator, "tool": card.tool,
        "produced_dimension": card.produced_dimension, "surface_treatment": card.surface_treatment,
        "article_number": card.article_number, "material_granulate": card.material_granulate,
        "coating": card.coating, "thickness": card.thickness, "width": card.width,
        "u_profile": card.u_profile, "surface": card.surface, "gloss": card.gloss,
        "notes": card.notes, "footer_processed_by": card.footer_processed_by,
        "footer_approved_by": card.footer_approved_by,
        "parameters": [_parse_parameter(p).model_dump() for p in params_raw],
    }

    xlsx_bytes = xlsx_exporter.build_xlsx(card_dict)

    stem = Path(card.original_filename).stem
    filename = f"{stem}.xlsx"

    card.status = "exported"
    card.updated_at = datetime.utcnow()
    card.updated_by = current_user.email
    db.commit()

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
