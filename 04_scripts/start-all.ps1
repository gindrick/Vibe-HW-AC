# Spustí všechny sdílené služby a projekty na pozadí (bez viditelných oken)
# Použití: cd c:/jja && ./04_scripts/start-all.ps1
# Logy: c:/jja/logs/<název-služby>.log

$root = "C:\jja"
$logDir = "$root\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

# Node.js 20 je potřeba pro Vite/frontend
$node20Path = "C:\tools\node20"
if (Test-Path $node20Path) {
    $env:PATH = "$node20Path;$env:PATH"
} else {
    Write-Warning "Node.js 20 nenalezen v $node20Path - frontend (Vite) nemusí fungovat!"
}

# uv je potřeba pro většinu Python služeb
# Je nainstalován v profilu uživatele reporting – přidáme explicitně, aby fungovalo i pod SYSTEM
$uvPath = "C:\Users\reporting\AppData\Roaming\Python\Python312\Scripts"
if (Test-Path $uvPath) {
    $env:PATH = "$uvPath;$env:PATH"
} else {
    Write-Warning "uv nenalezen v $uvPath - služby s 'uv run' nemusí fungovat!"
}

# --- Načtení .env souborů do prostředí procesu ---
# Start-Process dědí env proměnné z rodičovského procesu,
# proto je musíme nastavit zde před spuštěním child procesů.

function Import-EnvFile {
    param([string]$Path, [switch]$Force)
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $parts = $line -split '=', 2
        if ($parts.Count -eq 2) {
            $key = $parts[0].Trim()
            $val = $parts[1].Trim().Trim('"').Trim("'")
            if ($key -and ($Force -or -not [System.Environment]::GetEnvironmentVariable($key, "Process"))) {
                [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
            }
        }
    }
}

Import-EnvFile "$root\.env"
Import-EnvFile "$root\02_litellm\.env"
Import-EnvFile "$root\01_mcp\.env"
# Backend .env sa načíta s Force — prekoná prípadné systémové premenné (napr. MSSQL_USER=sa)
Import-EnvFile "$root\hr_hiring\2_backend\.env" -Force
Import-EnvFile "$root\production_cards\2_backend\.env" -Force
Import-EnvFile "$root\production_cards_2\2_backend\.env" -Force

# --- Pomocná funkce pro spuštění služby na pozadí ---
# Každá služba dostane vlastní log soubor. Starý log se při startu přepíše.

function Start-Service-Background {
    param(
        [string]$Name,
        [string]$WorkDir,
        [string]$Command
    )
    $log = "$logDir\$Name.log"
    # Zabalíme do PS tak, aby se stdout i stderr přesměrovaly do logu
    $psCmd = "Set-Location '$WorkDir'; $Command *>> '$log'"
    $proc = Start-Process powershell.exe `
        -ArgumentList @("-NoProfile", "-NonInteractive", "-Command", $psCmd) `
        -WindowStyle Hidden `
        -PassThru
    Write-Host "  [OK] $Name  (PID $($proc.Id))  → $log"
    return $proc
}

Write-Host ""
Write-Host "Spouštím JJA služby na pozadí..."
Write-Host ""

# --- Sdílené služby ---

Start-Service-Background `
    -Name "01-mcp" `
    -WorkDir "$root\01_mcp" `
    -Command "uv run python server.py"

Start-Service-Background `
    -Name "02-litellm" `
    -WorkDir "$root\02_litellm" `
    -Command "uv run litellm --config litellm_config.yaml --port 4000"

Start-Service-Background `
    -Name "03-router" `
    -WorkDir "$root\03_router" `
    -Command "uv run python -m uvicorn main:app --host 0.0.0.0 --port 8000"

# --- Projekty ---

Start-Service-Background `
    -Name "react-assistant" `
    -WorkDir "$root\react_assistant\3_web" `
    -Command "uv run python -m uvicorn app:app --host 127.0.0.1 --port 8001"

Start-Service-Background `
    -Name "hr-demo" `
    -WorkDir "$root\hr_demo" `
    -Command "& '$root\hr_demo\.venv\Scripts\python.exe' -m uvicorn server:app --host 127.0.0.1 --port 8003"

Start-Service-Background `
    -Name "hr-hiring-backend" `
    -WorkDir "$root\hr_hiring\2_backend" `
    -Command "& '$root\hr_hiring\2_backend\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 0.0.0.0 --port 8010"

Start-Service-Background `
    -Name "hr-hiring-frontend" `
    -WorkDir "$root\hr_hiring\3_frontend" `
    -Command "& 'C:\tools\node20\node.exe' .\node_modules\vite\bin\vite.js --host 0.0.0.0 --port 5173"

Start-Service-Background `
    -Name "production-cards-backend" `
    -WorkDir "$root\production_cards\2_backend" `
    -Command "& '$root\production_cards\2_backend\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 0.0.0.0 --port 8011"

Start-Service-Background `
    -Name "production-cards-frontend" `
    -WorkDir "$root\production_cards\3_frontend" `
    -Command "& 'C:\tools\node20\node.exe' .\node_modules\vite\bin\vite.js --host 0.0.0.0 --port 5174"

Start-Service-Background `
    -Name "production-cards-2-backend" `
    -WorkDir "$root\production_cards_2\2_backend" `
    -Command "& '$root\production_cards_2\2_backend\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 0.0.0.0 --port 8012"

Start-Service-Background `
    -Name "production-cards-2-frontend" `
    -WorkDir "$root\production_cards_2\3_frontend" `
    -Command "& 'C:\tools\node20\node.exe' .\node_modules\vite\bin\vite.js --host 0.0.0.0 --port 5175"

Write-Host ""
Write-Host "Všechny služby spuštěny na pozadí (bez oken)."
Write-Host ""
Write-Host "Porty:"
Write-Host "  8000 - Router (vstupní bod)"
Write-Host "  4000 - LiteLLM proxy"
Write-Host "  8001 - react_assistant web UI"
Write-Host "  8002 - MCP server"
Write-Host "  8003 - HR demo"
Write-Host "  8010 - HR Hiring backend"
Write-Host "  5173 - HR Hiring frontend (dev)"
Write-Host "  8011 - Production Cards backend"
Write-Host "  5174 - Production Cards frontend (dev)"
Write-Host "  8012 - Production Cards 2 backend"
Write-Host "  5175 - Production Cards 2 frontend (dev)"
Write-Host ""
Write-Host "Logy: $logDir\"
