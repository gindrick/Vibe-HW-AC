from __future__ import annotations

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def render_page_as_png_b64(pdf_path: str, page_number: int = 0, dpi: int = 150) -> str:
    """
    Render a single PDF page as a base64-encoded PNG.

    Args:
        pdf_path: Absolute path to the PDF file
        page_number: Zero-based page index
        dpi: Resolution (150 is a good balance between quality and size)

    Returns:
        Base64-encoded PNG string, or raises ValueError on failure
    """
    import fitz  # PyMuPDF

    path = Path(pdf_path)
    if not path.exists():
        raise ValueError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(path))
    try:
        if page_number >= len(doc):
            raise ValueError(f"Page {page_number} does not exist (PDF has {len(doc)} pages)")

        page = doc[page_number]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")
        return base64.b64encode(png_bytes).decode("ascii")
    finally:
        doc.close()


def get_page_count(pdf_path: str) -> int:
    import fitz
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count
