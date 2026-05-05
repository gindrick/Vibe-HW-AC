$ErrorActionPreference = "SilentlyContinue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runDir = Join-Path $root ".run"

if (-not (Test-Path $runDir)) {
    Write-Host "No running-state directory found. Nothing to stop."
    exit 0
}

foreach ($name in @("web", "mcp", "litellm")) {
    $pidFile = Join-Path $runDir "$name.pid"
    if (-not (Test-Path $pidFile)) {
        Write-Host "$name is not running (pid file missing)."
        continue
    }

    $procId = Get-Content -Path $pidFile -Raw
    if ($procId -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $procId -Force
        Write-Host "Stopped $name (PID $procId)"
    }
    else {
        Write-Host "$name pid file found, process already stopped."
    }

    Remove-Item $pidFile -Force
}

foreach ($port in @(8000, 8002, 4000)) {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        $listenerPid = $listener.OwningProcess
        if ($listenerPid -and (Get-Process -Id $listenerPid -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $listenerPid -Force
            Write-Host "Stopped lingering listener PID $listenerPid on port $port"
        }
    }
}

Write-Host "Native services stop sequence finished."