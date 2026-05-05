$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$mode = if ($env:RUN_MODE) { $env:RUN_MODE } else { "native" }

if ($mode -eq "docker") {
    & (Join-Path $root "scripts/start-docker.ps1")
    exit $LASTEXITCODE
}

& (Join-Path $root "scripts/start-native.ps1")
exit $LASTEXITCODE
