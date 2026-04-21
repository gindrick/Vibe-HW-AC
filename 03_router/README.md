# Router — Hranipex

Reverse proxy pro všechny interní webové aplikace. Běží na portu `8000`.

Konfigurace aplikací je v `apps.json` — router načítá změny za běhu, bez restartu.

## Aplikace

| URL | Cíl | Popis |
|-----|-----|-------|
| `http://erp.hranipex.net:8000/hr_hiring/` | `localhost:5173` | HR Hiring — frontend SPA |
| `http://erp.hranipex.net:8000/hr_hiring_api/` | `localhost:8010` | HR Hiring — backend API |
| `http://erp.hranipex.net:8000/react_assistant/` | `localhost:8001` | React Assistant |
| `http://erp.hranipex.net:8000/hr_demo/` | `localhost:8003` | HR Demo |

## Přidání nové aplikace

Přidejte záznam do `apps.json`:

```json
{
  "path": "nova_aplikace",
  "target": "http://localhost:8004",
  "strip_prefix": false,
  "description": "Popis nové aplikace"
}
```

- `strip_prefix: true` — router odstraní prefix cesty před předáním požadavku (používá `hr_hiring_api`)
- `strip_prefix: false` — cesta se předává beze změny

## Spuštění

```powershell
cd C:\jja\03_router
uv run python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Nebo přes `C:\jja\04_scripts\start-all.ps1` (doporučeno).

## Správa všech služeb

```powershell
# Start všech služeb na pozadí (bez oken)
C:\jja\04_scripts\start-all.ps1

# Stop všech služeb
C:\jja\04_scripts\stop-all.ps1
```

Služby jsou registrovány jako Windows Task Scheduler úloha `JJA-StartAll`
a spouštějí se automaticky při startu Windows jako `HRANIPEX\reporting`.

Logy jednotlivých služeb: `C:\jja\logs\`
