$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "Starting LiteLLM stack (Postgres + LiteLLM) via Docker Compose..."
Push-Location (Join-Path $root "0_litellm")
docker compose up -d
Pop-Location

Write-Host "Starting MCP server via Docker Compose..."
Push-Location (Join-Path $root "1_mcp")
docker compose up -d --build
Pop-Location

Write-Host "Starting web UI natively..."
Push-Location (Join-Path $root "3_web")
uv run uvicorn app:app --host 0.0.0.0 --port 8080
Pop-Location