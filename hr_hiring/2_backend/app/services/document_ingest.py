from __future__ import annotations


from pathlib import Path
from uuid import uuid4
import fitz  # PyMuPDF

# Optional imports for DOCX/DOC
try:
    import docx  # python-docx
except ImportError:
    docx = None
try:
    import mammoth  # for DOC to DOCX/Markdown
except ImportError:
    mammoth = None


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def store_binary_file(root: Path, bucket: str, entity_id: str, original_name: str, payload: bytes) -> Path:
    safe_name = original_name.replace("\\", "_").replace("/", "_").strip() or "file.bin"
    doc_dir = root / bucket / entity_id
    ensure_dir(doc_dir)
    file_path = doc_dir / f"{uuid4()}_{safe_name}"
    file_path.write_bytes(payload)
    return file_path


def store_text_file(root: Path, bucket: str, entity_id: str, content: str) -> Path:
    doc_dir = root / bucket / entity_id
    ensure_dir(doc_dir)
    file_path = doc_dir / f"{uuid4()}_inline.txt"
    file_path.write_text(content, encoding="utf-8")
    return file_path



def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF and return as Markdown."""
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        parts = [page.get_text("text") for page in doc]
        return "\n".join(parts).strip()
    finally:
        doc.close()

def extract_text_from_docx(content: bytes) -> str:
    """Extract text from DOCX and return as Markdown. Adds diagnostic info for debugging."""
    if docx is None:
        return "[python-docx not installed]"
    try:
        from io import BytesIO
        doc = docx.Document(BytesIO(content))
        lines = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                # Simple heading detection
                if para.style.name.lower().startswith("heading"):
                    level = ''.join(filter(str.isdigit, para.style.name)) or '1'
                    lines.append(f"{'#'*int(level)} {text}")
                else:
                    lines.append(text)
        result = '\n\n'.join(lines)
        # Diagnostic: prepend marker and encoding info
        return f"[DOCX->MD UTF-8 OK]\n{result}"
    except Exception as e:
        import base64
        # If parsing fails, return base64 for debugging
        return f"[DOCX ERROR: {e}]\nBASE64:\n" + base64.b64encode(content).decode("ascii")

def extract_text_from_doc(content: bytes) -> str:
    """Extract text from legacy DOC (OLE2 binary) using antiword, with mammoth as fallback for DOCX-disguised-as-DOC."""
    import subprocess, tempfile, os
    # Try antiword first (handles true legacy .doc OLE2 format)
    try:
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        result = subprocess.run(
            ["antiword", "-m", "UTF-8.txt", tmp_path],
            capture_output=True, timeout=30
        )
        os.unlink(tmp_path)
        if result.returncode == 0 and result.stdout:
            return result.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    # Fallback: mammoth (works for DOCX files saved with .doc extension)
    if mammoth is not None:
        try:
            from io import BytesIO
            result = mammoth.convert_to_markdown(BytesIO(content))
            return result.value.strip()
        except Exception:
            pass
    return "[DOC extraction failed: antiword and mammoth both unavailable or failed]"

def extract_text_from_md(content: bytes) -> str:
    """Return Markdown as-is (decode)."""
    for encoding in ("utf-8", "cp1250", "latin1"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return ""

def extract_text_from_txt(content: bytes) -> str:
    """Convert plain text to Markdown (basic)."""
    for encoding in ("utf-8", "cp1250", "latin1"):
        try:
            text = content.decode(encoding).strip()
            # Optionally, wrap lines >120 chars for readability
            return text
        except UnicodeDecodeError:
            continue
    return ""

def extract_text_universal(content: bytes, mime_type: str, filename: str) -> str:
    """Universal text extraction to Markdown for PDF, DOCX, DOC, MD, TXT."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf" or mime_type == "application/pdf":
        return extract_text_from_pdf(content)
    elif ext == ".docx" or mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_text_from_docx(content)
    elif ext == ".doc" or mime_type == "application/msword":
        return extract_text_from_doc(content)
    elif ext == ".md" or mime_type == "text/markdown":
        return extract_text_from_md(content)
    elif ext == ".txt" or mime_type == "text/plain":
        return extract_text_from_txt(content)
    # fallback: try text
    return extract_text_from_txt(content)

# For backward compatibility, alias the old function name
extract_text_from_payload = extract_text_universal
