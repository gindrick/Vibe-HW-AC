$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runDir = Join-Path $root ".run"

if (-not (Test-Path $runDir)) {
	Write-Host "No run directory found. Nothing to stop."
	exit 0
}

foreach ($name in @("frontend", "backend", "mcp", "litellm")) {
	$pidFile = Join-Path $runDir "$name.pid"
	if (-not (Test-Path $pidFile)) {
		continue
	}

	$pidValue = (Get-Content -Path $pidFile -Raw).Trim()
	if ($pidValue -and (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
		Stop-Process -Id $pidValue -Force
		Write-Host "Stopped $name (PID $pidValue)."
	}
	Remove-Item -Path $pidFile -Force
}

Write-Host "Native services stopped."
