$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Push-Location (Join-Path $root "0_litellm")
try {
	docker compose up -d
}
finally {
	Pop-Location
}

Write-Host "LiteLLM docker container started."
Write-Host "For full stack in docker mode, add dedicated Dockerfiles for mcp/backend/frontend in next iteration."
