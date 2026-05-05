# HR Hiring — Frontend SPA

React + Vite SPA. Přístupná přes router na `/hr_hiring/`.

- **Dev server:** port `5173`
- **Veřejná URL:** `http://erp.hranipex.net:8000/hr_hiring/`
- **Auth:** LDAP session cookie (přihlášení přes `/hr_hiring_api/auth/login`)

## Spuštění

```powershell
# Node.js 20 je vyžadován (systémový node je příliš starý)
C:\tools\node20\node.exe .\node_modules\vite\bin\vite.js --host 0.0.0.0 --port 5173
```

Nebo přes `C:\jja\04_scripts\start-all.ps1` (doporučeno).

## Obrazovky

- Seznam pozic (filtrování, vytvoření, archivace)
- Detail pozice (seznam kandidátů, přidání kandidáta, upload dokumentů k pozici)
- Detail kandidáta (spuštění AI hodnocení, polling výsledků, tabulka kritérií)

## Konfigurace (`.env`)

```
VITE_PUBLIC_BASE_PATH=/hr_hiring/
VITE_API_ROUTER_PATH=/hr_hiring_api
VITE_AUTH_MODE=ldap
```

## Build

```powershell
C:\tools\node20\node.exe .\node_modules\.bin\vite build
```
