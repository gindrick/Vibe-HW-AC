$ErrorActionPreference = "Continue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "Stopping MCP Docker Compose stack..."
Push-Location (Join-Path $root "1_mcp")
docker compose down
Pop-Location

Write-Host "Stopping LiteLLM Docker Compose stack..."
Push-Location (Join-Path $root "0_litellm")
docker compose down
Pop-Location

Write-Host "Docker services stopped."