$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Push-Location (Join-Path $root "0_litellm")
try {
	docker compose down
}
finally {
	Pop-Location
}

Write-Host "LiteLLM docker container stopped."
