$ErrorActionPreference = "Stop"

# Clear VIRTUAL_ENV so uv picks up each project's own .venv instead of an unrelated one
$env:VIRTUAL_ENV = $null

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runDir = Join-Path $root ".run"
$logDir = Join-Path $root "logs"

New-Item -ItemType Directory -Force -Path $runDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not $env:LITELLM_MASTER_KEY) { $env:LITELLM_MASTER_KEY = "sk-mysecretkey" }
if (-not $env:LITELLM_BASE_URL)   { $env:LITELLM_BASE_URL = "http://localhost:4000" }
if (-not $env:LITELLM_API_KEY)    { $env:LITELLM_API_KEY = $env:LITELLM_MASTER_KEY }
if (-not $env:EMBEDDINGS_MODEL)   { $env:EMBEDDINGS_MODEL = "oai-text-embedding-3-small" }
if (-not $env:MCP_SERVER_URL)     { $env:MCP_SERVER_URL = "http://localhost:8002" }
if (-not $env:WEB_PORT)           { $env:WEB_PORT = "8001" }

function Resolve-UvExecutable {
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCmd -and $uvCmd.Source) { return $uvCmd.Source }
    throw "Command 'uv' was not found. Install uv and ensure uv.exe is in PATH."
}

$uvExecutable = Resolve-UvExecutable

function Start-ServiceProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $pidFile = Join-Path $runDir "$Name.pid"
    if (Test-Path $pidFile) {
        $existingPid = Get-Content -Path $pidFile -Raw
        if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
            Write-Host "$Name is already running (PID $existingPid)."
            return
        }
        Remove-Item $pidFile -Force
    }

    $stdoutPath = Join-Path $logDir "$Name.out.log"
    $stderrPath = Join-Path $logDir "$Name.err.log"

    Write-Host "Launching $Name..."
    $process = Start-Process -FilePath $Command -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
    Set-Content -Path $pidFile -Value $process.Id
    Write-Host "Started $Name (PID $($process.Id))"
}

# Sdílené služby jsou v 01_mcp a 02_litellm — startuje je 04_scripts/start-all.ps1
# Tento skript startuje pouze web UI react_assistant

Start-ServiceProcess -Name "web" -WorkingDirectory (Join-Path $root "3_web") -Command $uvExecutable -Arguments @(
    "run", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", $env:WEB_PORT
)

Write-Host "react_assistant web UI started."
Write-Host "Web UI (internal): http://127.0.0.1:$($env:WEB_PORT)"
Write-Host "Web UI (public):   http://localhost:8000/react_assistant"
