$ErrorActionPreference = "Stop"

$routerRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceRoot = (Resolve-Path (Join-Path $routerRoot "..")).Path
$runDir = Join-Path $routerRoot ".run"
$logDir = Join-Path $routerRoot "logs"

New-Item -ItemType Directory -Force -Path $runDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$aiFrameworkRoot = Join-Path $workspaceRoot "react_assistant"
$dashboardHrRoot = Join-Path $workspaceRoot "hr_demo"
$hrHiringBackendRoot = Join-Path $workspaceRoot "dashboards\hr_hiring\2_backend"
$hrHiringFrontendRoot = Join-Path $workspaceRoot "dashboards\hr_hiring\3_frontend"

function Resolve-Executable {
    param([Parameter(Mandatory = $true)][string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd -or -not $cmd.Source) {
        throw "Command '$Name' was not found in PATH."
    }
    return $cmd.Source
}

function Start-ManagedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $pidFile = Join-Path $runDir "$Name.pid"
    if (Test-Path $pidFile) {
        $existing = (Get-Content -Path $pidFile -Raw).Trim()
        if ($existing -and (Get-Process -Id $existing -ErrorAction SilentlyContinue)) {
            Write-Host "$Name is already running (PID $existing)."
            return
        }
        Remove-Item -Path $pidFile -Force
    }

    $stdoutPath = Join-Path $logDir "$Name.out.log"
    $stderrPath = Join-Path $logDir "$Name.err.log"

    Write-Host "Launching ${Name}: $Command $($Arguments -join ' ')"
    $proc = Start-Process -FilePath $Command -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
    Set-Content -Path $pidFile -Value $proc.Id
    Write-Host "Started $Name (PID $($proc.Id))"
}

function Wait-ForPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $listening = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listening) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

$uvExe = Resolve-Executable -Name "uv"
$npmExe = Resolve-Executable -Name "npm"

if (-not (Test-Path $aiFrameworkRoot)) {
    throw "Missing folder: $aiFrameworkRoot"
}
if (-not (Test-Path $dashboardHrRoot)) {
    throw "Missing folder: $dashboardHrRoot"
}
if (-not (Test-Path $hrHiringBackendRoot)) {
    throw "Missing folder: $hrHiringBackendRoot"
}
if (-not (Test-Path $hrHiringFrontendRoot)) {
    throw "Missing folder: $hrHiringFrontendRoot"
}

Write-Host "Starting react_assistant runtime bundle..."
& (Join-Path $aiFrameworkRoot "start-services.ps1")

Start-Sleep -Seconds 2

Start-ManagedProcess -Name "dashboard-hr" -WorkingDirectory $dashboardHrRoot -Command $uvExe -Arguments @("run", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8003")
Start-ManagedProcess -Name "hr-hiring-backend" -WorkingDirectory $hrHiringBackendRoot -Command $uvExe -Arguments @("run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010")
Start-ManagedProcess -Name "hr-hiring-frontend" -WorkingDirectory $hrHiringFrontendRoot -Command $npmExe -Arguments @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173")
Start-ManagedProcess -Name "router" -WorkingDirectory $routerRoot -Command $uvExe -Arguments @("run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000")

$ports = @(4000, 8000, 8001, 8002, 8003, 8010, 5173)
$failed = @()
foreach ($port in $ports) {
    if (-not (Wait-ForPort -Port $port -TimeoutSeconds 30)) {
        $failed += $port
    }
}

if ($failed.Count -gt 0) {
    Write-Warning "Some ports are not listening: $($failed -join ', ')"
    Write-Warning "Check logs in $logDir and app logs in react_assistant/logs."
}

Write-Host "All requested services were started."
Write-Host "AI Framework:  http://localhost:8000/ai_framework"
Write-Host "HR Dashboard:  http://localhost:8000/dashboard/static/index.html"
Write-Host "HR Hiring:     http://localhost:8000/hr_hiring"
Write-Host "HR Hiring API: http://localhost:8000/hr_hiring_api/health"
