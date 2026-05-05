<#
.SYNOPSIS
    Start all native services (LiteLLM, MCP, Web) for Task Scheduler.

.DESCRIPTION
    This wrapper invokes `scripts\start-native.ps1` from the repository root.
    The called script launches services in background and writes PID files to
    `.run`. Optionally loads an `.env` file from the repo root to set environment
    variables before starting.

.USAGE
    powershell -NoProfile -ExecutionPolicy Bypass -File "C:\jja\ai_framework\start-services.ps1"

    Example for Task Scheduler `Action` field:
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\jja\ai_framework\start-services.ps1"
#>

param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = 'Stop'

# $root is the repo root where this script lives
$root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition)).Path

# Load optional env file with lines like KEY=VALUE (ignores blank lines and # comments)
$envPath = Join-Path $root $EnvFile
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $parts = $line -split '=', 2
        if ($parts.Count -eq 2) {
            $name = $parts[0].Trim()
            $value = $parts[1].Trim()
            if ($value.Length -ge 2) {
                if (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"'))) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
            }
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Minimal sensible defaults if not already set
if (-not $env:LITELLM_MASTER_KEY) { $env:LITELLM_MASTER_KEY = 'sk-mysecretkey' }
if (-not $env:LITELLM_BASE_URL) { $env:LITELLM_BASE_URL = 'http://localhost:4000' }
if (-not $env:LITELLM_API_KEY) { $env:LITELLM_API_KEY = $env:LITELLM_MASTER_KEY }
if (-not $env:EMBEDDINGS_MODEL) { $env:EMBEDDINGS_MODEL = 'oai-text-embedding-3-small' }
if (-not $env:MCP_SERVER_URL) { $env:MCP_SERVER_URL = 'http://localhost:8002' }
if (-not $env:WEB_PORT) { $env:WEB_PORT = '8001' }

Write-Host "Starting native services from: $root"

$script = Join-Path $root 'scripts\start-native.ps1'
if (-not (Test-Path $script)) {
    Write-Error "Required script not found: $script"
    exit 1
}

# Invoke the existing start script which already backgrounds processes and writes PID files
& $script

Write-Host "Invoked start script. Check logs in $root\logs and PID files in $root\.run"
