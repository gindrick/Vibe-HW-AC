# JJA — Workspace

Monorepo pro AI a HR aplikace. Sdílená infrastruktura (MCP, LiteLLM, Router) běží jako společné služby pro všechny projekty. Každý projekt je dostupný přes centrální reverse proxy na portu **8000**.

---

## Struktura rootu

```
c:\jja\
├── 01_mcp/              Sdílený MCP server — všechny nástroje pro AI agenty
├── 02_litellm/          Sdílený LiteLLM proxy — jednotný přístup k LLM providerům
├── 03_router/           Reverse proxy — routuje URL cesty na interní služby (port 8000)
├── 04_scripts/          Obslužné skripty — spuštění a zastavení všech služeb
│
├── react_assistant/     Projekt: AI agenti (ReAct, Plan-Execute, Workflow) + SharePoint
├── hr_hiring/           Projekt: HR hiring platforma (backend + React frontend)
├── production_cards/    Projekt: Výrobní karty — extrakce dat z PDF nastavovacích karet
├── hr_demo/             Projekt: HR demo dashboard
├── ollama_hrx/          Projekt: Ollama lokální LLM aplikace (standalone)
│
├── .env                 Globální API klíče (není v gitu)
└── .env.example         Šablona globálního .env
```

---

## Porty

| Port | Služba | Popis |
|------|--------|-------|
| **8000** | `03_router` | Vstupní bod — všechny projekty přes tento port |
| 8001 | `react_assistant` | Web UI pro AI agenty |
| 8002 | `01_mcp` | MCP server |
| 8003 | `hr_demo` | HR demo dashboard |
| 4000 | `02_litellm` | LiteLLM proxy |
| 8010 | `hr_hiring` backend | HR hiring API |
| 5173 | `hr_hiring` frontend | React dev server |
| 8011 | `production_cards` backend | Production Cards API |
| 5174 | `production_cards` frontend | React dev server |

---

## URL adresy projektů

Vše přes router na `http://localhost:8000`:

| URL | Projekt |
|-----|---------|
| `http://localhost:8000/react_assistant` | React Assistant |
| `http://localhost:8000/dashboard` | HR Demo |
| `http://localhost:8000/hr_hiring` | HR Hiring (frontend) |
| `http://localhost:8000/hr_hiring_api` | HR Hiring (API) |
| `http://localhost:8000/production_cards` | Production Cards (frontend) |
| `http://localhost:8000/production_cards_api` | Production Cards (API) |

> `ollama_hrx` není zatím naroutován — spouští se samostatně.

---

## Spuštění

```powershell
# Spustí všechny sdílené služby + projekty na pozadí (bez oken)
./04_scripts/start-all.ps1

# Zobrazí stav každé služby (port, uptime)
./04_scripts/status.ps1

# Zastaví vše a spustí znovu
./04_scripts/restart.ps1
```

> Při startu serveru se `start-all.ps1` spouští automaticky přes Windows Scheduled Task `JJA\StartAll` (s 30s zpožděním po bootu).

---

## Konfigurace (.env)

Konfigurace je vrstvená — globální klíče v rootu, projektová specifika v každém projektu:

```
c:\jja\.env                ← globální (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...)
c:\jja\01_mcp\.env         ← MCP specifické (MSSQL, TAVILY, WOLFRAM)
c:\jja\02_litellm\.env     ← LiteLLM specifické (LITELLM_MASTER_KEY, OLLAMA_API_BASE)
c:\jja\<projekt>\.env      ← projektové (MODEL=..., MCP_TOOLS=..., ...)
```

Každý adresář obsahuje `.env.example` jako šablonu. Nikdy necommituj `.env` soubory.

---

## Přidání nového projektu

### 1. Vytvoř složku projektu

```
c:\jja\<nazev_projektu>\
├── .env.example     ← dokumentuj potřebné proměnné
├── .env
├── pyproject.toml   (nebo package.json pro Node)
└── README.md
```

### 2. Zvol volný port

Viz tabulka portů výše. Aplikace musí naslouchat na `127.0.0.1` (nebo `0.0.0.0` pokud potřebuješ přístup ze sítě).

### 3. Zaregistruj projekt v routeru

Přidej záznam do [03_router/apps.json](03_router/apps.json):

```json
{
  "path": "nazev_v_url",
  "target": "http://127.0.0.1:8020",
  "strip_prefix": false,
  "description": "Popis projektu"
}
```

> Router načítá `apps.json` dynamicky — **restart routeru není potřeba**.

### 4. Přidej projekt do start-all.ps1

V [04_scripts/start-all.ps1](04_scripts/start-all.ps1) přidej blok na konec sekce `# --- Projekty ---`:

```powershell
Start-Service-Background `
    -Name "nazev-projektu" `
    -WorkDir "$root\nazev_projektu" `
    -Command "uv run python -m uvicorn main:app --host 127.0.0.1 --port 8020"
```

A do výpisu portů na konci souboru:

```powershell
Write-Host "  8020 - Název projektu"
```

### 5. Přidej projekt do status.ps1

V [04_scripts/status.ps1](04_scripts/status.ps1) přidej řádek do pole `$services`:

```powershell
@{ Name = "nazev-projektu"; Port = 8020; Desc = "Popis projektu" }
```

### 6. Nastav .env

Pokud projekt potřebuje sdílené služby, přidej do `.env` projektu:

```env
LITELLM_BASE_URL=http://127.0.0.1:4000    # LiteLLM proxy
LITELLM_API_KEY=sk-mysecretkey
MCP_SERVER_URL=http://127.0.0.1:8002/mcp  # MCP server
```

---

## Aktuální projekty

### react_assistant
AI agenti s různými reasoning patterny (ReAct, Plan-Execute, Workflow). Zahrnuje SharePoint ingestion pipeline a Chroma vector DB pro retrieval. Web UI dostupné přes router.

### hr_hiring
Kompletní HR hiring platforma. FastAPI backend s LangGraph workflow pro AI evaluaci kandidátů, React + Vite frontend s Azure AD (MSAL) autentizací.

### production_cards
Extrakce dat z PDF nastavovacích karet extruzních linek. FastAPI backend s LiteLLM extrakcí (PyMuPDF + LLM structured output), React + Vite frontend se split-view (náhled PDF | editace), export do XLSX. MSSQL schema `production_cards`.

### hr_demo
Jednoduchý HR demo dashboard. FastAPI backend se statickým frontendem.

### ollama_hrx
Standalone aplikace postavená na Ollama lokálním LLM. Má vlastní web UI a knowledge base. Zatím není integrována do routeru.
