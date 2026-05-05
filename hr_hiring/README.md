# HR Hiring Evaluation Platform

On-prem platforma pro hodnocení uchazečů o zaměstnání. Kombinuje FastAPI backend, LangGraph AI workflow, LiteLLM proxy, MCP nástroje a React SPA s tmavým/světlým režimem.

## Struktura projektu

```
hr_hiring/
├── 1_agents/        Standalone CLI agenti (SQLAlchemy + LiteLLM, bez FastAPI)
├── 2_backend/       FastAPI backend (auth, uploady, evaluace, API)
├── 3_frontend/      React SPA (Vite, React Router, @tanstack/react-table)
└── scripts/         Start/stop skripty (native)
```

Sdílené služby (mimo tento repozitář):
- `01_mcp/` — MCP server s nástroji pro HR (port 8002)
- `0_litellm/` — LiteLLM proxy (port 4000)
- `03_router/` — Centrální reverse proxy (port 8000)

## Funkční oblasti

### Správa pozic (`/hr_hiring/`)
- Tabulka pracovních pozic se sortováním, filtrováním a globálním vyhledáváním
- Modální formulář pro přidání pozice: název, popis, datum, platové rozmezí Od/Do, přiložení JD (drag & drop nebo text)
- Archivace pozic
- Tmavý/světlý režim (systémový + ruční přepínač)

### Detail pozice (`/hr_hiring/positions/:id`)
- Záložka **Kandidáti**: tabulka s hodnocením (score bar, doporučení badge), tlačítko pro spuštění AI hodnocení, modal pro přidání kandidáta s drag & drop CV
- Záložka **Podklady pozice**: nahrání Job Description a doplňkových dokumentů (soubor nebo text)
- Tlačítko **Dashboard** — zobrazí se po dokončení prvního hodnocení

### Dashboard pozice (`/hr_hiring/positions/:id/dashboard`)
- Tmavý header s názvem pozice a priority kritérii (z JD analýzy)
- Statistiky: celkem / nejlepší shoda / zvážit / nevhodný / čeká
- Filtrovací záložky podle doporučení
- Grid karet kandidátů s criterion bary, tagy silných stránek, rationale a nice-to-have

### Detail kandidáta (`/hr_hiring/candidates/:id`)
- Nahrání dokumentů: CV, přepis pohovoru, ostatní
- Spuštění AI hodnocení s real-time pollingem statusu
- Zobrazení evaluation karty: rationale, silné stránky / mezery / red flags, must-have a nice-to-have bary, doporučené otázky k pohovoru

## AI Evaluation workflow

```
HR nahraje CV →
  backend extrahuje text (PyMuPDF) →
    HR spustí hodnocení →
      LangGraph pipeline (background task):
        1. load_documents  — načte JD + CV z DB
        2. jd_analyzer     — LLM extrahuje kritéria (must-have / nice-to-have)
        3. evaluator       — LLM porovná kandidáta s kritérii, skóre 1–5
        4. output_formatter — uloží CandidateEvaluationCard do DB
      frontend polling → zobrazí kartu
```

LLM volání používají `response_format=json_object` pro strukturovaný výstup. Schéma: `CandidateEvaluationCard` (pydantic, `2_backend/app/workflows/schemas.py`).

## 1_agents — Standalone CLI

Agenti běží nezávisle na FastAPI, přistupují přímo do MSSQL přes SQLAlchemy. Sdílejí workflow kód s backendem (přes sys.path).

```bash
cd 1_agents
uv sync
# Hodnotit jednoho kandidáta:
python run.py candidate --id <candidate_uuid>
# Batch hodnocení všech čekajících kandidátů pozice:
python run.py position --id <position_uuid>
# Výpis kandidátů:
python run.py list --position-id <position_uuid>
```

## MCP nástroje (01_mcp)

| Nástroj | Popis |
|---|---|
| `hr_ping` | Health check |
| `hr_read_document` | Text dokumentu dle doc_id |
| `hr_list_documents` | Dokumenty pozice |
| `hr_build_jd_context` | Sloučený context JD pro LLM |
| `hr_build_candidate_context` | Sloučený context kandidáta pro LLM |
| `hr_save_evaluation` | Uloží evaluation kartu do DB |
| `hr_get_evaluation` | Načte evaluation záznam kandidáta |
| `hr_list_position_candidates` | Kandidáti pozice s eval statusem |
| `hr_run_evaluation` | Spustí hodnocení přes backend API |
| `hr_get_position_dashboard` | Plná dashboard data (stats + karty) |

## Rychlý start

```powershell
# 1. Závislosti
cd 2_backend && uv sync
cd ../3_frontend && npm install
cd ../1_agents && uv sync   # volitelné, jen pro CLI

# 2. Prostředí
copy 2_backend\.env.example 2_backend\.env   # vyplňte MSSQL, LITELLM_*, AUTH_MODE

# 3. Start (ze složky jja)
powershell 04_scripts\start-all.ps1

# 4. Otevřít
# http://localhost:8000/hr_hiring
```

## Integrace s routerem

| Cesta | Cíl | Poznámka |
|---|---|---|
| `/hr_hiring` | `http://localhost:5173` | SPA, strip_prefix=false |
| `/hr_hiring_api` | `http://localhost:8010` | Backend API, strip_prefix=true |

Frontend volá API přes `/hr_hiring_api` (single-origin přes router).

## Databáze

MSSQL Server, schéma `hr_eval`. Tabulky se vytvoří automaticky při prvním startu (`AUTO_CREATE_SCHEMA=true`). Sloupce přidané migrací: `SalaryFrom`, `SalaryTo`, `SalaryVisible`, `OpenedAt`.

## Seed demo dat

```powershell
powershell scripts\seed-demo.ps1
```

Vytvoří jednoho HM, jednu pozici, dva kandidáty a jedno dokončené hodnocení.
