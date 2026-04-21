from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import text

from db import get_connection


def ping() -> str:
    return "hr-hiring-mcp:ok"


def _row_to_doc_dict(row: Any) -> dict[str, Any]:
    return {
        "document_id": row.DocumentId,
        "document_type": row.DocumentType,
        "file_name": row.FileName,
        "mime_type": row.MimeType,
        "is_processed": bool(row.IsProcessed),
    }


def read_document(doc_id: str) -> str:
    """Return extracted text of one position/candidate document by doc id."""
    query = text(
        """
        SELECT TOP 1 ExtractedText
        FROM hr_eval.PositionDocuments
        WHERE DocumentId = :doc_id
        UNION ALL
        SELECT TOP 1 ExtractedText
        FROM hr_eval.CandidateDocuments
        WHERE DocumentId = :doc_id
        """
    )
    with get_connection() as conn:
        row = conn.execute(query, {"doc_id": doc_id}).first()
    if row is None:
        raise ValueError(f"Document not found: {doc_id}")
    return row.ExtractedText or ""


def list_documents(position_id: str) -> list[dict[str, Any]]:
    """List position-level documents (JD + supplementary) for one position."""
    query = text(
        """
        SELECT DocumentId, DocumentType, FileName, MimeType, IsProcessed
        FROM hr_eval.PositionDocuments
        WHERE PositionId = :position_id
        ORDER BY CreatedAt ASC
        """
    )
    with get_connection() as conn:
        rows = conn.execute(query, {"position_id": position_id}).fetchall()
    return [_row_to_doc_dict(row) for row in rows]


def build_jd_context(position_id: str) -> str:
    """Build one context string from JD and supplementary position docs."""
    query = text(
        """
        SELECT DocumentType, FileName, ExtractedText
        FROM hr_eval.PositionDocuments
        WHERE PositionId = :position_id
          AND IsProcessed = 1
          AND DocumentType IN ('job_description', 'supplementary')
        ORDER BY CASE WHEN DocumentType = 'job_description' THEN 0 ELSE 1 END, CreatedAt ASC
        """
    )
    with get_connection() as conn:
        rows = conn.execute(query, {"position_id": position_id}).fetchall()

    parts: list[str] = []
    for row in rows:
        doc_type = row.DocumentType or "unknown"
        file_name = row.FileName or "unnamed"
        extracted_text = (row.ExtractedText or "").strip()
        if not extracted_text:
            continue
        parts.append(f"[{doc_type}] {file_name}\n{extracted_text}")
    return "\n\n---\n\n".join(parts)


def build_candidate_context(candidate_id: str) -> str:
    """Build one context string from candidate CV and interview transcript docs."""
    query = text(
        """
        SELECT DocumentType, FileName, ExtractedText
        FROM hr_eval.CandidateDocuments
        WHERE CandidateId = :candidate_id
          AND IsProcessed = 1
          AND DocumentType IN ('cv', 'interview_transcript', 'other')
        ORDER BY CASE
            WHEN DocumentType = 'cv' THEN 0
            WHEN DocumentType = 'interview_transcript' THEN 1
            ELSE 2
        END, CreatedAt ASC
        """
    )
    with get_connection() as conn:
        rows = conn.execute(query, {"candidate_id": candidate_id}).fetchall()

    parts: list[str] = []
    for row in rows:
        doc_type = row.DocumentType or "unknown"
        file_name = row.FileName or "unnamed"
        extracted_text = (row.ExtractedText or "").strip()
        if not extracted_text:
            continue
        parts.append(f"[{doc_type}] {file_name}\n{extracted_text}")
    return "\n\n---\n\n".join(parts)


def _extract_scores(card: dict[str, Any]) -> tuple[float, float, str, str, str]:
    recommendation = str(card.get("recommendation", "")).strip().upper() or "ZVAZIT"
    overall_score = float(card.get("overall_score", 0.0) or 0.0)
    must_have_score = float(card.get("must_have_score", 0.0) or 0.0)
    model_used = str(card.get("model_used", "unknown"))
    schema_version = str(card.get("schema_version", "1.0.0"))
    return overall_score, must_have_score, recommendation, model_used, schema_version


def save_evaluation(candidate_id: str, card_json: str) -> None:
    """Insert or update evaluation record for candidate."""
    card = json.loads(card_json)
    position_id = str(card.get("position_id", ""))
    if not position_id:
        query_position = text(
            """
            SELECT TOP 1 PositionId
            FROM hr_eval.Candidates
            WHERE CandidateId = :candidate_id
            """
        )
        with get_connection() as conn:
            row = conn.execute(query_position, {"candidate_id": candidate_id}).first()
        if row is None:
            raise ValueError(f"Candidate not found: {candidate_id}")
        position_id = row.PositionId

    overall_score, must_have_score, recommendation, model_used, schema_version = _extract_scores(card)
    now = datetime.utcnow()

    with get_connection() as conn:
        existing = conn.execute(
            text(
                """
                SELECT TOP 1 EvaluationId
                FROM hr_eval.Evaluations
                WHERE CandidateId = :candidate_id
                """
            ),
            {"candidate_id": candidate_id},
        ).first()

        if existing:
            conn.execute(
                text(
                    """
                    UPDATE hr_eval.Evaluations
                    SET Status = 'completed',
                        Recommendation = :recommendation,
                        OverallScore = :overall_score,
                        MustHaveScore = :must_have_score,
                        EvaluationJson = :evaluation_json,
                        ErrorMessage = '',
                        ModelUsed = :model_used,
                        SchemaVersion = :schema_version,
                        UpdatedAt = :updated_at,
                        UpdatedBy = 'mcp'
                    WHERE CandidateId = :candidate_id
                    """
                ),
                {
                    "candidate_id": candidate_id,
                    "recommendation": recommendation,
                    "overall_score": overall_score,
                    "must_have_score": must_have_score,
                    "evaluation_json": card_json,
                    "model_used": model_used,
                    "schema_version": schema_version,
                    "updated_at": now,
                },
            )
            return

        conn.execute(
            text(
                """
                INSERT INTO hr_eval.Evaluations (
                    EvaluationId,
                    CandidateId,
                    PositionId,
                    Status,
                    Recommendation,
                    OverallScore,
                    MustHaveScore,
                    EvaluationJson,
                    ErrorMessage,
                    ModelUsed,
                    SchemaVersion,
                    CreatedAt,
                    CreatedBy,
                    UpdatedAt,
                    UpdatedBy
                )
                VALUES (
                    :evaluation_id,
                    :candidate_id,
                    :position_id,
                    'completed',
                    :recommendation,
                    :overall_score,
                    :must_have_score,
                    :evaluation_json,
                    NULL,
                    :model_used,
                    :schema_version,
                    :created_at,
                    'mcp',
                    :updated_at,
                    'mcp'
                )
                """
            ),
            {
                "evaluation_id": str(uuid4()),
                "candidate_id": candidate_id,
                "position_id": position_id,
                "recommendation": recommendation,
                "overall_score": overall_score,
                "must_have_score": must_have_score,
                "evaluation_json": card_json,
                "model_used": model_used,
                "schema_version": schema_version,
                "created_at": now,
                "updated_at": now,
            },
        )


def list_position_candidates(position_id: str) -> list[dict[str, Any]]:
    """List all candidates for a position with their evaluation status."""
    query = text(
        """
        SELECT c.CandidateId, c.FullName, c.Email, c.ExternalRef,
               e.Status AS EvalStatus, e.Recommendation, e.OverallScore, e.MustHaveScore
        FROM hr_eval.Candidates c
        LEFT JOIN hr_eval.Evaluations e ON e.CandidateId = c.CandidateId
        WHERE c.PositionId = :position_id
        ORDER BY c.CreatedAt ASC
        """
    )
    with get_connection() as conn:
        rows = conn.execute(query, {"position_id": position_id}).fetchall()
    return [
        {
            "candidate_id": row.CandidateId,
            "full_name": row.FullName,
            "email": row.Email,
            "external_ref": row.ExternalRef,
            "evaluation_status": row.EvalStatus,
            "recommendation": row.Recommendation,
            "overall_score": float(row.OverallScore) if row.OverallScore is not None else None,
            "must_have_score": float(row.MustHaveScore) if row.MustHaveScore is not None else None,
        }
        for row in rows
    ]


def run_evaluation(candidate_id: str) -> dict[str, Any]:
    """Trigger evaluation for a candidate via backend API (POST /evaluations/{id})."""
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8010")
    resp = httpx.post(f"{backend_url}/evaluations/{candidate_id}", timeout=180.0)
    if resp.status_code >= 400:
        raise RuntimeError(f"Evaluation API error {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def get_position_dashboard(position_id: str) -> dict[str, Any]:
    """Return full dashboard data for a position: stats + all candidates with evaluation cards."""
    query = text(
        """
        SELECT c.CandidateId, c.FullName, c.Email, c.ExternalRef,
               e.Status AS EvalStatus, e.Recommendation,
               e.OverallScore, e.MustHaveScore, e.EvaluationJson
        FROM hr_eval.Candidates c
        LEFT JOIN hr_eval.Evaluations e ON e.CandidateId = c.CandidateId
        WHERE c.PositionId = :position_id
        ORDER BY e.OverallScore DESC
        """
    )
    with get_connection() as conn:
        rows = conn.execute(query, {"position_id": position_id}).fetchall()

    stats = {"total": len(rows), "recommended": 0, "consider": 0, "not_recommended": 0, "pending": 0}
    candidates = []

    for row in rows:
        rec = (row.Recommendation or "").upper()
        if rec == "DOPORUCIT":
            stats["recommended"] += 1
        elif rec == "ZVAZIT":
            stats["consider"] += 1
        elif rec == "NEDOPORUCIT":
            stats["not_recommended"] += 1
        else:
            stats["pending"] += 1

        card = None
        if row.EvaluationJson:
            try:
                card = json.loads(row.EvaluationJson)
            except json.JSONDecodeError:
                pass

        candidates.append(
            {
                "candidate_id": row.CandidateId,
                "full_name": row.FullName,
                "email": row.Email,
                "external_ref": row.ExternalRef,
                "evaluation_status": row.EvalStatus,
                "recommendation": row.Recommendation,
                "overall_score": float(row.OverallScore) if row.OverallScore is not None else None,
                "must_have_score": float(row.MustHaveScore) if row.MustHaveScore is not None else None,
                "card": card,
            }
        )

    return {"position_id": position_id, "stats": stats, "candidates": candidates}


def get_evaluation(candidate_id: str) -> dict[str, Any]:
    """Load latest evaluation record for candidate."""
    query = text(
        """
        SELECT TOP 1
            EvaluationId,
            CandidateId,
            PositionId,
            Status,
            Recommendation,
            OverallScore,
            MustHaveScore,
            EvaluationJson,
            ErrorMessage,
            ModelUsed,
            SchemaVersion,
            UpdatedAt
        FROM hr_eval.Evaluations
        WHERE CandidateId = :candidate_id
        ORDER BY UpdatedAt DESC
        """
    )
    with get_connection() as conn:
        row = conn.execute(query, {"candidate_id": candidate_id}).first()

    if row is None:
        return {"status": "not_found", "candidate_id": candidate_id}

    parsed_card: dict[str, Any] | None = None
    if row.EvaluationJson:
        try:
            parsed_card = json.loads(row.EvaluationJson)
        except json.JSONDecodeError:
            parsed_card = None

    return {
        "evaluation_id": row.EvaluationId,
        "candidate_id": row.CandidateId,
        "position_id": row.PositionId,
        "status": row.Status,
        "recommendation": row.Recommendation,
        "overall_score": float(row.OverallScore) if row.OverallScore is not None else None,
        "must_have_score": float(row.MustHaveScore) if row.MustHaveScore is not None else None,
        "card": parsed_card,
        "error": row.ErrorMessage,
        "model_used": row.ModelUsed,
        "schema_version": row.SchemaVersion,
        "updated_at": row.UpdatedAt.isoformat() if row.UpdatedAt else None,
    }
