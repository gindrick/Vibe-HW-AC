$ErrorActionPreference = "Stop"

$routerRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceRoot = (Resolve-Path (Join-Path $routerRoot "..")).Path
$runDir = Join-Path $routerRoot ".run"

function Stop-ManagedProcess {
    param([Parameter(Mandatory = $true)][string]$Name)

    $pidFile = Join-Path $runDir "$Name.pid"
    if (-not (Test-Path $pidFile)) {
        return
    }

    $pidValue = (Get-Content -Path $pidFile -Raw).Trim()
    if ($pidValue -and (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $pidValue -Force
        Write-Host "Stopped $Name (PID $pidValue)."
    }

    Remove-Item -Path $pidFile -Force
}

foreach ($name in @("router", "hr-hiring-frontend", "hr-hiring-backend", "dashboard-hr")) {
    Stop-ManagedProcess -Name $name
}

$aiFrameworkStop = Join-Path $workspaceRoot "react_assistant\scripts\stop-native.ps1"
if (Test-Path $aiFrameworkStop) {
    & $aiFrameworkStop
}

Write-Host "All managed app services were stopped."
