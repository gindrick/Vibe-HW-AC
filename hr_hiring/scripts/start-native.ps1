$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runDir = Join-Path $root ".run"
$logDir = Join-Path $root "logs"

New-Item -ItemType Directory -Force -Path $runDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not $env:LITELLM_MASTER_KEY) { $env:LITELLM_MASTER_KEY = "sk-local" }
if (-not $env:LITELLM_BASE_URL) { $env:LITELLM_BASE_URL = "http://127.0.0.1:4000" }
if (-not $env:LITELLM_API_KEY) { $env:LITELLM_API_KEY = $env:LITELLM_MASTER_KEY }
if (-not $env:BACKEND_PORT) { $env:BACKEND_PORT = "8010" }
if (-not $env:FRONTEND_PORT) { $env:FRONTEND_PORT = "5173" }

function Resolve-UvExecutable {
	$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
	if ($uvCmd -and $uvCmd.Source) {
		return $uvCmd.Source
	}
	throw "Command 'uv' was not found. Install uv and ensure it is on PATH."
}

function Start-ServiceProcess {
	param(
		[Parameter(Mandatory = $true)][string]$Name,
		[Parameter(Mandatory = $true)][string]$WorkingDirectory,
		[Parameter(Mandatory = $true)][string]$Command,
		[Parameter(Mandatory = $true)][string[]]$Arguments
	)

	$pidFile = Join-Path $runDir "${Name}.pid"
	if (Test-Path $pidFile) {
		$existingPid = Get-Content -Path $pidFile -Raw
		if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
			Write-Host "${Name} is already running (PID $existingPid)."
			return
		}
		Remove-Item $pidFile -Force
	}

	$stdoutPath = Join-Path $logDir "${Name}.out.log"
	$stderrPath = Join-Path $logDir "${Name}.err.log"

	Write-Host "Launching ${Name}: $Command $($Arguments -join ' ')"
	$process = Start-Process -FilePath $Command -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
	Set-Content -Path $pidFile -Value $process.Id
	Write-Host "Started ${Name} (PID $($process.Id))"
}

$uv = Resolve-UvExecutable

Start-ServiceProcess -Name "litellm" -WorkingDirectory (Join-Path $root "0_litellm") -Command $uv -Arguments @(
	"run",
	"--with",
	"litellm[proxy]",
	"litellm",
	"--config",
	"litellm_config.yaml",
	"--host",
	"127.0.0.1",
	"--port",
	"4000",
	"--num_workers",
	"1"
)

Start-Sleep -Seconds 2

Start-ServiceProcess -Name "mcp" -WorkingDirectory (Join-Path $root "1_mcp") -Command $uv -Arguments @("run", "python", "server.py")

Start-Sleep -Seconds 2

Start-ServiceProcess -Name "backend" -WorkingDirectory (Join-Path $root "2_backend") -Command $uv -Arguments @("run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $env:BACKEND_PORT)

Start-Sleep -Seconds 2

$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) {
	throw "npm is not available in PATH. Install Node.js LTS before starting frontend."
}

Start-ServiceProcess -Name "frontend" -WorkingDirectory (Join-Path $root "3_frontend") -Command $npmCmd.Source -Arguments @("run", "dev", "--", "--host", "127.0.0.1", "--port", $env:FRONTEND_PORT)

Write-Host "All native services started."
Write-Host "Router frontend URL: http://localhost:8000/hr_hiring"
Write-Host "Router API URL:      http://localhost:8000/hr_hiring_api/health"
