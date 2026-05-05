$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location (Join-Path $root "2_backend")
try {
    uv run python scripts/seed_demo.py
}
finally {
    Pop-Location
}
