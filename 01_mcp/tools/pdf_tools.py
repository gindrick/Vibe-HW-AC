from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def extract_pdf_text(file_path: str) -> str:
    """
    Extract plain text from a PDF file using PyMuPDF.

    Args:
        file_path: Absolute path to the PDF file

    Returns:
        Extracted text content, or error message starting with "Error:"
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return "Error: PyMuPDF (fitz) is not installed. Run: pip install pymupdf"

    path = Path(file_path)
    if not path.exists():
        return f"Error: File '{file_path}' does not exist"
    if not path.is_file():
        return f"Error: '{file_path}' is not a file"
    if path.suffix.lower() != ".pdf":
        return f"Error: '{file_path}' is not a PDF file"

    try:
        doc = fitz.open(str(path))
        pages: list[str] = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text.strip():
                pages.append(f"--- Strana {i} ---\n{text.strip()}")
        doc.close()

        if not pages:
            return "Error: PDF neobsahuje žádný extrahovatelný text (může jít o skenovaný obrázek bez OCR vrstvy)"

        result = "\n\n".join(pages)
        logger.info("extract_pdf_text: %s -> %d chars across %d pages", file_path, len(result), len(pages))
        return result

    except Exception as exc:
        logger.error("extract_pdf_text failed for %s: %s", file_path, exc)
        return f"Error: {exc}"
