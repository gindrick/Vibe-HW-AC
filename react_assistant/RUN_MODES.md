# Run Modes (Docker + Native)

Projekt podporuje oba režimy spuštění:

- Docker režim (kde je Docker dostupný)
- Native režim (bez Dockeru, přímo jako procesy)

Skripty jsou v adresáři `scripts/` a fungují pro oba scénáře.

## Rychlé spuštění

### Windows (PowerShell)

Native režim:

```powershell
./scripts/start-native.ps1
```

Stop native režimu:

```powershell
./scripts/stop-native.ps1
```

Docker režim:

```powershell
./scripts/start-docker.ps1
```

Stop Docker režimu:

```powershell
./scripts/stop-docker.ps1
```

### Linux/macOS (bash)

Jednorázově nastavte spustitelný bit:

```bash
chmod +x scripts/*.sh
```

Native režim:

```bash
./scripts/start-native.sh
```

Stop native režimu:

```bash
./scripts/stop-native.sh
```

Docker režim:

```bash
./scripts/start-docker.sh
```

Stop Docker režimu:

```bash
./scripts/stop-docker.sh
```

## Předpoklady

- `uv` nainstalované v systému
- pro native režim běžící PostgreSQL pro LiteLLM (`DATABASE_URL`)
- nastavené klíče pro model providery v `0_litellm/litellm_config.yaml`

## Důležité URL

- LiteLLM: `http://localhost:4000`
- MCP server (base URL): `http://localhost:8002`
- MCP endpoint: `http://localhost:8002/mcp`
- Web UI: `http://localhost:8000` (default v native mode)

Port webu lze změnit přes `WEB_PORT` (např. `WEB_PORT=8080`).

## Health-check poznámka

- `GET http://localhost:8002/mcp` může vrátit `406` (u MCP streamable endpointu je to očekávané při obyčejném browser GET).
- Pro rychlou kontrolu stačí ověřit, že běží proces MCP a web (`http://localhost:8080`), případně použít MCP klienta z frameworku.

Poznámka: v `MCP_SERVER_URL` používejte base URL (`http://localhost:8002`). Klient je kompatibilní i s variantou končící `/mcp`.