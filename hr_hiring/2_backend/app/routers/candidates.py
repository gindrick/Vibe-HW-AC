from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user, get_db
from app.models import Candidate, CandidateDocument, Position
from app.models import Evaluation
from app.schemas import CandidateCreateRequest, CandidateDocumentSummary, CandidateResponse, CandidateUpdateRequest, CurrentUser, DocumentUploadResponse
from app.services.document_ingest import extract_text_from_payload, store_binary_file, store_text_file
from app.workflows.hashing import refresh_candidate_eval_staleness

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _position_for_owner(db: Session, position_id: str, owner_id: str):
    return db.query(Position).filter(Position.position_id == position_id, Position.owner_id == owner_id).first()


@router.post("", response_model=CandidateResponse)
def create_candidate(
    payload: CandidateCreateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CandidateResponse:
    position = _position_for_owner(db, payload.position_id, current_user.user_id)
    if position is None and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="Position not found")

    now = datetime.utcnow()
    name = payload.full_name.strip() or "_"
    candidate = Candidate(
        candidate_id=str(uuid4()),
        position_id=payload.position_id,
        full_name=name,
        email=payload.email.strip(),
        phone=payload.phone.strip(),
        external_ref=payload.external_ref.strip(),
        notes=payload.notes.strip(),
        created_at=now,
        updated_at=now,
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    return CandidateResponse(
        candidate_id=candidate.candidate_id,
        position_id=candidate.position_id,
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        external_ref=candidate.external_ref,
        notes=candidate.notes,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CandidateResponse:
    candidate = (
        db.query(Candidate)
        .join(Position, Position.position_id == Candidate.position_id)
        .filter(Candidate.candidate_id == candidate_id)
        .first()
    )

    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if current_user.role != "admin":
        position = db.query(Position).filter(Position.position_id == candidate.position_id).first()
        if position is None or position.owner_id != current_user.user_id:
            raise HTTPException(status_code=404, detail="Candidate not found")

    return CandidateResponse(
        candidate_id=candidate.candidate_id,
        position_id=candidate.position_id,
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        external_ref=candidate.external_ref,
        notes=candidate.notes,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


@router.get("/{candidate_id}/documents", response_model=list[CandidateDocumentSummary])
def list_candidate_documents(
    candidate_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[CandidateDocumentSummary]:
    candidate = (
        db.query(Candidate)
        .join(Position, Position.position_id == Candidate.position_id)
        .filter(Candidate.candidate_id == candidate_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if current_user.role != "admin":
        position = db.query(Position).filter(Position.position_id == candidate.position_id).first()
        if position is None or position.owner_id != current_user.user_id:
            raise HTTPException(status_code=404, detail="Candidate not found")

    docs = (
        db.query(CandidateDocument)
        .filter(CandidateDocument.candidate_id == candidate_id)
        .order_by(CandidateDocument.created_at)
        .all()
    )
    return [
        CandidateDocumentSummary(
            document_id=d.document_id,
            file_name=d.file_name,
            document_type=d.document_type,
            is_text=d.mime_type == "text/plain",
            extracted_chars=len(d.extracted_text or ""),
        )
        for d in docs
    ]


@router.delete("/{candidate_id}/documents/{document_id}")
def delete_candidate_document(
    candidate_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    candidate = (
        db.query(Candidate)
        .join(Position, Position.position_id == Candidate.position_id)
        .filter(Candidate.candidate_id == candidate_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if current_user.role != "admin":
        position = db.query(Position).filter(Position.position_id == candidate.position_id).first()
        if position is None or position.owner_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not allowed")

    doc = db.query(CandidateDocument).filter(
        CandidateDocument.document_id == document_id,
        CandidateDocument.candidate_id == candidate_id,
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except Exception:
        pass

    db.delete(doc)
    db.commit()
    refresh_candidate_eval_staleness(db, candidate_id)
    return {"deleted": document_id}


@router.post("/{candidate_id}/documents", response_model=DocumentUploadResponse)
async def upload_candidate_document(
    candidate_id: str,
    document_type: str = Form(...),
    file: UploadFile | None = File(default=None),
    text_content: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentUploadResponse:
    allowed_types = {"cv", "interview_transcript", "other"}
    if document_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid document_type")

    candidate = (
        db.query(Candidate)
        .join(Position, Position.position_id == Candidate.position_id)
        .filter(Candidate.candidate_id == candidate_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if current_user.role != "admin":
        position = db.query(Position).filter(Position.position_id == candidate.position_id).first()
        if position is None or position.owner_id != current_user.user_id:
            raise HTTPException(status_code=404, detail="Candidate not found")

    if file is None and not (text_content and text_content.strip()):
        raise HTTPException(status_code=400, detail="Provide file or text_content")

    upload_root = Path(settings.upload_root)
    now = datetime.utcnow()

    if file is not None:
        payload = await file.read()
        mime_type = file.content_type or "application/octet-stream"
        file_path = store_binary_file(upload_root, "candidates", candidate_id, file.filename or "upload.bin", payload)
        extracted = extract_text_from_payload(payload, mime_type, file.filename or "upload.bin")
        file_name = file.filename or file_path.name
    else:
        inline = (text_content or "").strip()
        file_path = store_text_file(upload_root, "candidates", candidate_id, inline)
        mime_type = "text/plain"
        extracted = inline
        file_name = file_path.name

    row = CandidateDocument(
        document_id=str(uuid4()),
        candidate_id=candidate_id,
        document_type=document_type,
        file_name=file_name,
        file_path=str(file_path),
        mime_type=mime_type,
        extracted_text=extracted,
        is_processed=bool(extracted.strip()),
        created_at=now,
        updated_at=now,
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    refresh_candidate_eval_staleness(db, candidate_id)

    return DocumentUploadResponse(
        document_id=row.document_id,
        file_name=row.file_name,
        mime_type=row.mime_type,
        is_processed=bool(row.is_processed),
        extracted_chars=len(row.extracted_text or ""),
    )


@router.patch("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(
    candidate_id: str,
    payload: CandidateUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CandidateResponse:
    candidate = (
        db.query(Candidate)
        .join(Position, Position.position_id == Candidate.position_id)
        .filter(Candidate.candidate_id == candidate_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if current_user.role != "admin":
        position = db.query(Position).filter(Position.position_id == candidate.position_id).first()
        if position is None or position.owner_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not allowed")

    if payload.full_name is not None:
        candidate.full_name = payload.full_name.strip()
    if payload.email is not None:
        candidate.email = payload.email.strip()
    if payload.phone is not None:
        candidate.phone = payload.phone.strip()
    if payload.external_ref is not None:
        candidate.external_ref = payload.external_ref.strip()
    if payload.notes is not None:
        candidate.notes = payload.notes.strip()

    candidate.updated_at = datetime.utcnow()
    candidate.updated_by = current_user.email
    db.commit()
    db.refresh(candidate)

    return CandidateResponse(
        candidate_id=candidate.candidate_id,
        position_id=candidate.position_id,
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        external_ref=candidate.external_ref,
        notes=candidate.notes,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


@router.delete("/{candidate_id}")
def delete_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    candidate = (
        db.query(Candidate)
        .join(Position, Position.position_id == Candidate.position_id)
        .filter(Candidate.candidate_id == candidate_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if current_user.role != "admin":
        position = db.query(Position).filter(Position.position_id == candidate.position_id).first()
        if position is None or position.owner_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not allowed")

    db.query(CandidateDocument).filter(CandidateDocument.candidate_id == candidate_id).delete()
    db.query(Evaluation).filter(Evaluation.candidate_id == candidate_id).delete()
    db.delete(candidate)
    db.commit()
    return {"deleted": candidate_id}
