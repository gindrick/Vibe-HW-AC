# Aktivace venv, pokud existuje
$venvPath = Join-Path $PSScriptRoot "../.venv/Scripts/Activate.ps1"
if (Test-Path $venvPath) { . $venvPath }

# Spuštění backendu na správném portu
uvicorn server:app --host 0.0.0.0 --port 8003
