# Production Cards 2

Extraction of structured data from scanned PDF setup cards of extrusion lines.

A PDF is uploaded, a multi-agent pipeline with an **LLM supervisor** extracts all fields, the user reviews and edits the result in a split-view UI (PDF preview | editable form), and exports to XLSX.

---

## Architecture

```
3_frontend/    React + Vite UI  (port 5175)
2_backend/     FastAPI + MSSQL  (port 8012)
```

### Multi-agent extraction pipeline

The core of the backend is a **LLM Supervisor** pattern in `2_backend/app/services/agent_pipeline.py`.

```
Upload PDF
    │
    ▼
render PNG (PyMuPDF)
    │
    ▼
┌─────────────────────────────────────────────┐
│            LLM SUPERVISOR (Claude)          │
│  Decides which sub-agents to call, in what  │
│  order, and how many revision cycles to run │
│                                             │
│  Tools available to the supervisor:         │
│    read_document   → document-reader agent  │
│    extract_form    → form-extractor agent   │
│    review_draft    → validator-reviewer     │
│    finalize_result → end pipeline           │
└─────────────────────────────────────────────┘
    │
    ▼
Structured CardData saved to MSSQL
```

Each sub-agent runs in its own isolated Claude session via `claude-agent-sdk query()`.

**Pipeline limits** (constants in `agent_pipeline.py`):

| Constant | Default | Scope |
|---|---|---|
| `SUPERVISOR_MAX_ITERATIONS` | 10 | Max tool-call rounds for the LLM supervisor |
| `SUBAGENT_MAX_TURNS` | 5 | Max internal turns per sub-agent session |

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, React Router, Vite |
| Backend | FastAPI, SQLAlchemy, Uvicorn |
| Database | MSSQL (schema `production_cards`) |
| PDF rendering | PyMuPDF (fitz) |
| LLM orchestration | Anthropic API + `claude-agent-sdk` |
| Auth | LDAP (Active Directory) / dev bypass |
| Export | openpyxl (XLSX) |

---

## Setup

### Backend

```bash
cd 2_backend
cp .env.example .env        # fill in secrets
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8012 --reload
```

### Frontend

```bash
cd 3_frontend
npm install
cp .env.example .env
npm run dev                 # http://127.0.0.1:5175
```

---

## Configuration (`2_backend/.env`)

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(from root .env)* | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model used for all agents |
| `MSSQL_HOST` | `localhost` | MSSQL server host |
| `MSSQL_PORT` | `1433` | MSSQL port |
| `MSSQL_DB` | `production_cards` | Database name |
| `MSSQL_USER` | `sa` | DB user |
| `MSSQL_PASSWORD` | | DB password |
| `AUTH_MODE` | `ldap` | `ldap` or `dev` |
| `DEV_AUTH_BYPASS` | `true` | Skip auth in dev mode |
| `LDAP_SERVER` | | `ldap://dc.example.local` |
| `LDAP_DOMAIN` | | `example.local` |
| `LDAP_ALLOWED_USERS` | | Comma-separated list, empty = all |
| `BACKEND_PORT` | `8012` | Backend listen port |
| `SESSION_SECRET` | | Change before deploying |
| `UPLOAD_ROOT` | `./storage/uploads` | PDF storage path |
| `AUTO_CREATE_SCHEMA` | `true` | Create DB tables on startup |

---

## Ports

| Port | Service |
|---|---|
| **8012** | Backend API |
| **5175** | Frontend dev server |

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/cards/upload` | Upload PDF, triggers extraction |
| `GET` | `/api/cards` | List cards with filters and pagination |
| `GET` | `/api/cards/{id}` | Get single card |
| `PATCH` | `/api/cards/{id}` | Update card fields |
| `GET` | `/api/cards/{id}/export` | Download XLSX |
| `GET` | `/api/cards/{id}/pdf` | Stream original PDF |
| `GET` | `/auth/logout` | Logout (LDAP session) |
| `GET` | `/me` | Current user info |

---

## Logs

```
2_backend/logs/
├── backend.out.log   application log
├── auth.log          login / logout events
└── costs.log         per-agent token usage and cost estimates
```

The `costs.log` records every agent invocation: supervisor iterations and each sub-agent call with token counts.
