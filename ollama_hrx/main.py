import os
import re
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, TYPE_CHECKING

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rank_bm25 import BM25Okapi
import ollama
from ollama import chat
from llm_wrapper import chat_completion_text

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIType
else:
    OpenAIType = Any

load_dotenv()

BASE_DIR = Path(__file__).parent
KB_DIR = BASE_DIR / "kb"
WEB_DIR = BASE_DIR / "web"

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "oai-gpt-4.1-nano")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://0.0.0.0:4000")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "dummy-key")
TOP_K = int(os.getenv("TOP_K", "8"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "2.5"))

MAX_CHARS = 1400
OVERLAP_CHARS = 200

logger = logging.getLogger("perf")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ----------------------------
# KB ingest + chunking
# ----------------------------

def read_md_files(root: Path) -> List[Dict[str, Any]]:
    docs = []
    for p in root.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        docs.append({"path": str(p.relative_to(root)), "text": text})
    return docs


def strip_md(md: str) -> str:
    md = re.sub(r"```.*?```", " ", md, flags=re.S)      # code blocks
    md = re.sub(r"`[^`]*`", " ", md)                    # inline code
    md = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", md)       # images
    md = re.sub(r"\[[^\]]*\]\([^)]+\)", r" ", md)       # links
    md = re.sub(r"[>*_~`]+", " ", md)                   # md symbols
    md = re.sub(r"\s+", " ", md).strip()
    return md


def split_by_headings(md_text: str) -> List[Dict[str, str]]:
    """
    Rozdělí markdown podle nadpisů (#, ##, ###...). Pro POC to dává lepší relevanci než čisté odstavce.
    Vrací list bloků: {"title": "...", "body": "..."}
    """
    lines = md_text.splitlines()
    blocks = []
    title = "Úvod"
    buf = []

    def flush():
        nonlocal buf, title
        body = "\n".join(buf).strip()
        if body:
            blocks.append({"title": title, "body": body})
        buf = []

    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*)\s*$", line)
        if m:
            flush()
            title = m.group(2).strip()
        else:
            buf.append(line)

    flush()
    return blocks


def chunk_text(text: str, max_chars: int = MAX_CHARS, overlap_chars: int = OVERLAP_CHARS) -> List[str]:
    # chunking po odstavcích a skládání do bloků ~ max_chars
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    buf = ""

    for p in paras:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + "\n\n" + p).strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) > max_chars:
                for i in range(0, len(p), max_chars):
                    chunks.append(p[i:i + max_chars])
                buf = ""
            else:
                buf = p

    if buf:
        chunks.append(buf)

    # overlap
    if overlap_chars > 0 and len(chunks) > 1:
        overlapped = []
        prev_tail = ""
        for c in chunks:
            c2 = (prev_tail + "\n\n" + c).strip() if prev_tail else c
            overlapped.append(c2)
            prev_tail = c[-overlap_chars:]
        return overlapped

    return chunks


def tokenize(s: str) -> List[str]:
    s = s.lower()
    s = re.sub(r"[^a-zá-ž0-9]+", " ", s)
    return [t for t in s.split() if len(t) > 1]


class KBIndex:
    def __init__(self):
        self.chunks: List[Dict[str, Any]] = []
        self.bm25: Optional[BM25Okapi] = None
        self.corpus_tokens: List[List[str]] = []

    def build(self, kb_dir: Path):
        docs = read_md_files(kb_dir)
        chunks: List[Dict[str, Any]] = []

        for d in docs:
            # Nejdřív rozdělit podle nadpisů
            sections = split_by_headings(d["text"])
            chunk_no = 0

            for sec in sections:
                plain = strip_md(sec["body"])
                for ch in chunk_text(plain):
                    chunk_no += 1
                    chunks.append({
                        "id": f'{d["path"]}#chunk{chunk_no}',
                        "path": d["path"],
                        "section": sec["title"],
                        "chunk_no": chunk_no,
                        "text": ch,
                    })

        self.chunks = chunks
        self.corpus_tokens = [tokenize(c["text"]) for c in self.chunks]
        self.bm25 = BM25Okapi(self.corpus_tokens)

    def search(self, query: str, top_k: int = TOP_K) -> List[Tuple[float, Dict[str, Any]]]:
        if not self.bm25 or not self.chunks:
            return []
        q_tokens = tokenize(query)
        scores = self.bm25.get_scores(q_tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [(float(score), self.chunks[idx]) for idx, score in ranked]


kb = KBIndex()
kb.build(KB_DIR)


# ----------------------------
# Ollama (chat)
# ----------------------------

def make_system_prompt(mode: str) -> str:
    base = (
        "Jsi firemní asistent. Odpovídej POUZE podle poskytnutého kontextu.\n"
        "Pokud odpověď v kontextu není, napiš přesně: 'V knowledge base k tomu nemám informace.'\n"
        "Nevymýšlej si nic mimo kontext.\n"
        "Každé důležité tvrzení zakonči citací ve formátu [číslo].\n"
    )

    if mode == "3_sentences":
        return base + "Odpověz maximálně ve 3 větách.\n"
    if mode == "quotes_only":
        return (
            "Vrať pouze DOSLOVNÉ citace z kontextu, přesně zkopírované.\n"
            "Každou citaci dej do uvozovek a přidej citaci zdroje [číslo].\n"
            "Nepřidávej žádný vlastní text. Pokud nic nenajdeš, napiš: 'V knowledge base k tomu nemám informace.'\n"
        )

    return base


def _fmt_ns(ns: Optional[int]) -> str:
    if ns is None:
        return "n/a"
    return f"{ns / 1_000_000_000:.3f}s"


def _tps(count: Optional[int], duration_ns: Optional[int]) -> str:
    if not count or not duration_ns:
        return "n/a"
    seconds = duration_ns / 1_000_000_000
    if seconds <= 0:
        return "n/a"
    return f"{count / seconds:.2f}"  # tokens per second


def call_ollama(question: str, context_blocks: List[Dict[str, Any]], mode: str) -> str:
    ctx_lines = []
    for i, b in enumerate(context_blocks, start=1):
        ctx_lines.append(
            f"[{i}] Soubor: {b['path']} | Sekce: {b.get('section','')} | chunk {b['chunk_no']}\n{b['text']}"
        )

    system = make_system_prompt(mode)

    t0 = time.perf_counter()
    resp = chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "KONTEXT:\n\n" + "\n\n---\n\n".join(ctx_lines) + "\n\nDOTAZ:\n" + question},
        ],
        options={"temperature": 0.1},
    )
    t1 = time.perf_counter()

    # Metrics from Ollama API (durations are nanoseconds)
    load_ns = resp.get("load_duration")
    prompt_ns = resp.get("prompt_eval_duration")
    eval_ns = resp.get("eval_duration")
    total_ns = resp.get("total_duration")
    prompt_count = resp.get("prompt_eval_count")
    eval_count = resp.get("eval_count")

    logger.info(
        "ollama timings total=%s load=%s prompt=%s eval=%s wall=%.3fs prompt_tokens=%s eval_tokens=%s prompt_tps=%s eval_tps=%s",
        _fmt_ns(total_ns),
        _fmt_ns(load_ns),
        _fmt_ns(prompt_ns),
        _fmt_ns(eval_ns),
        t1 - t0,
        prompt_count if prompt_count is not None else "n/a",
        eval_count if eval_count is not None else "n/a",
        _tps(prompt_count, prompt_ns),
        _tps(eval_count, eval_ns),
    )

    # python sdk vrací dict-like strukturu
    return resp["message"]["content"]


_openai_client: Optional[OpenAIType] = None


def get_openai_client() -> OpenAIType:
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    if OpenAI is None:
        raise RuntimeError("OpenAI client is not installed. Add openai to dependencies.")
    _openai_client = OpenAI(
        api_key=os.getenv("LITELLM_API_KEY", "dummy-key"),
        base_url=os.getenv("LITELLM_BASE_URL", "http://0.0.0.0:4000"),
    )
    return _openai_client


def call_llm(question: str, context_blocks: List[Dict[str, Any]], mode: str) -> str:
    if LLM_PROVIDER in {"ollama", "local"}:
        return call_ollama(question, context_blocks, mode)

    if LLM_PROVIDER in {"litellm", "openai"}:
        ctx_lines = []
        for i, b in enumerate(context_blocks, start=1):
            ctx_lines.append(
                f"[{i}] Soubor: {b['path']} | Sekce: {b.get('section','')} | chunk {b['chunk_no']}\n{b['text']}"
            )

        system = make_system_prompt(mode)
        return chat_completion_text(
            model=LITELLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "KONTEXT:\n\n" + "\n\n---\n\n".join(ctx_lines) + "\n\nDOTAZ:\n" + question},
            ],
            temperature=0.1,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")


# ----------------------------
# API + Web UI
# ----------------------------

app = FastAPI(title="KB POC (md-only)")
app.mount("/web", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


class AskIn(BaseModel):
    question: str
    mode: str = "normal"  # "normal" | "3_sentences" | "quotes_only"


class AskOut(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]


@app.get("/", response_class=HTMLResponse)
def home():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/web/", response_class=HTMLResponse)
def web_home():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/meta")
def meta():
    return {
        "model": OLLAMA_MODEL,
        "top_k": TOP_K,
        "min_score": MIN_SCORE,
    }


@app.post("/api/reload")
def reload_index():
    kb.build(KB_DIR)
    return {"ok": True, "chunks": len(kb.chunks)}


@app.post("/api/ask", response_model=AskOut)
def ask(inp: AskIn):
    t0 = time.perf_counter()
    hits = kb.search(inp.question, top_k=TOP_K)
    t1 = time.perf_counter()
    logger.info("kb.search time=%.3fs hits=%d", t1 - t0, len(hits))

    # gating: když není relevance, nevolat model
    if not hits or hits[0][0] < MIN_SCORE:
        return AskOut(answer="V knowledge base k tomu nemám informace.", sources=[])

    selected = [h[1] | {"score": h[0]} for h in hits]

    try:
        t2 = time.perf_counter()
        answer = call_llm(inp.question, selected, inp.mode)
        t3 = time.perf_counter()
        logger.info("llm.total time=%.3fs context_chunks=%d", t3 - t2, len(selected))
    except ollama.ResponseError as e:
        # Tohle je klíčové – uvidíš přesný důvod (404 model not found, 401 signin, atd.)
        return AskOut(
            answer=f"Ollama error {e.status_code}: {e.error}",
            sources=selected,
        )
    except Exception as e:
        return AskOut(
            answer=f"Chyba při volání Ollama: {type(e).__name__}: {e}",
            sources=selected,
        )

    return AskOut(answer=answer, sources=selected)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
