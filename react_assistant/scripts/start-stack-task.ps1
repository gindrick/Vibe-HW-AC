$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$taskLog = Join-Path $logDir "task-startup.log"
"`n[$(Get-Date -Format s)] Starting scheduled stack startup..." | Out-File -FilePath $taskLog -Append -Encoding utf8

# Ensure uv executable path is available when Task runs as SYSTEM
# Adjust this path if uv.exe is located elsewhere for your user
$uvCandidate = 'C:\Users\reporting\AppData\Roaming\Python\Python312\Scripts'
if (Test-Path $uvCandidate) {
    if (-not ($env:Path -like "*${uvCandidate}*")) {
        $env:Path = "$($env:Path);$uvCandidate"
        "[$(Get-Date -Format s)] Added $uvCandidate to PATH for task." | Out-File -FilePath $taskLog -Append -Encoding utf8
    }
} else {
    "[$(Get-Date -Format s)] uv candidate path not found: $uvCandidate" | Out-File -FilePath $taskLog -Append -Encoding utf8
}

function Wait-ForPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

try {
    Push-Location $root

    # Clean previous processes/listeners and start fresh
    & (Join-Path $root "scripts\stop-native.ps1") | Out-Null
    & (Join-Path $root "scripts\start-native.ps1") | Out-Null

    $ok4000 = Wait-ForPort -Port 4000 -TimeoutSeconds 40
    $ok8002 = Wait-ForPort -Port 8002 -TimeoutSeconds 40
    $ok8000 = Wait-ForPort -Port 8000 -TimeoutSeconds 40

    if (-not ($ok4000 -and $ok8002 -and $ok8000)) {
        "[$(Get-Date -Format s)] Startup failed. Ports state: 4000=$ok4000, 8002=$ok8002, 8000=$ok8000" | Out-File -FilePath $taskLog -Append -Encoding utf8
        throw "One or more services failed to start."
    }

    "[$(Get-Date -Format s)] Startup success. Ports listening: 4000, 8002, 8000" | Out-File -FilePath $taskLog -Append -Encoding utf8
}
catch {
    "[$(Get-Date -Format s)] Startup exception: $($_.Exception.Message)" | Out-File -FilePath $taskLog -Append -Encoding utf8
    throw
}
finally {
    Pop-Location
}