# HR Hiring — Backend API

FastAPI služba pro autentizaci, správu pozic, kandidátů a AI hodnocení.

- **Port:** `8010` (localhost only, přístupný přes router na `/hr_hiring_api`)
- **DB:** MSSQL `digin` na `192.168.41.43:1433`
- **Auth:** LDAP (`hranipex.net`) — viz `AUTH_MODE=ldap` v `.env`
- **LLM:** přes LiteLLM proxy na `http://127.0.0.1:4000`, model `oai-gpt-4.1-nano`

## Spuštění

```powershell
# Vždy použít venv Python, ne systémový!
C:\jja\hr_hiring\2_backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Nebo přes `C:\jja\04_scripts\start-all.ps1` (doporučeno).

## API endpointy

| Metoda | Cesta | Popis |
|--------|-------|-------|
| GET | `/health` | Stav služby |
| GET | `/auth/login` | Přihlašovací stránka (LDAP) |
| POST | `/auth/login` | Odeslání přihlašovacího formuláře |
| GET | `/auth/logout` | Odhlášení |
| GET | `/auth/status` | Stav session (používá frontend) |
| GET | `/me` | Přihlášený uživatel |
| GET | `/positions` | Seznam pozic |
| POST | `/positions` | Vytvoření pozice |
| PATCH | `/positions/{id}/archive` | Archivace pozice |
| POST | `/positions/{id}/documents` | Upload dokumentu k pozici |
| GET | `/candidates` | Seznam kandidátů |
| POST | `/candidates` | Vytvoření kandidáta |
| POST | `/candidates/{id}/documents` | Upload dokumentu ke kandidátovi |
| GET | `/evaluations/{candidate_id}` | Výsledek hodnocení |
| POST | `/evaluations/{candidate_id}` | Spuštění AI hodnocení |
| GET | `/llm-stats` | Statistiky LLM volání |

## Klíčové moduly

- `app/config.py` — nastavení prostředí a připojení k MSSQL
- `app/database.py` — SQLAlchemy engine/session
- `app/models.py` — ORM modely (Positions, Candidates, Evaluations, ...)
- `app/routers/auth_ldap.py` — LDAP přihlášení, session cookie
- `app/routers/` — REST endpointy
- `app/workflows/runner.py` — LangGraph orchestrace AI hodnocení
- `app/workflows/extractor.py` — extrakce textu z dokumentů (PDF, DOCX)

## Přihlášení

Povolení uživatelé jsou definováni v `.env`:
```
LDAP_ALLOWED_USERS=jindrich.jansa,petr.pazourek,eva.rablova,romana.basova
```

## Logy

- `logs/backend.out.log` — uvicorn + aplikační logy
- `logs/auth.log` — přihlašovací pokusy (LOGIN_SUCCESS / LOGIN_FAILED)
- `logs/costs.log` — náklady na LLM volání
