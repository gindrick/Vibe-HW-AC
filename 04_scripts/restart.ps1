# Zastaví všechny JJA služby a spustí je znovu přes start-all.ps1
# Použití: cd c:/jja && ./04_scripts/restart.ps1

$ports = @(8002, 4000, 8000, 8001, 8003, 8010, 5173)
$root  = "C:\jja"

Write-Host ""
Write-Host "Zastavuji JJA služby..." -ForegroundColor Yellow

$listening = netstat -ano | Select-String 'LISTENING'
$killedAny = $false

foreach ($port in $ports) {
    $match = $listening | Where-Object { $_ -match ":$port\s" }
    if ($match) {
        $pid_val = ($match | Select-Object -First 1) -replace '.*\s+(\d+)\s*$', '$1'
        $pid_int = [int]$pid_val.Trim()
        try {
            # Zastavíme celý strom procesů (uvicorn spouští worker child procesy)
            $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $pid_int }
            foreach ($child in $children) {
                Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
            }
            Stop-Process -Id $pid_int -Force -ErrorAction SilentlyContinue
            Write-Host "  Zastaven port :$port (PID $pid_int)" -ForegroundColor Gray
            $killedAny = $true
        } catch {
            Write-Host "  Port :$port – nelze zastavit (PID $pid_int): $_" -ForegroundColor Red
        }
    }
}

if (-not $killedAny) {
    Write-Host "  Žádná běžící služba nenalezena." -ForegroundColor Gray
}

Write-Host ""
Write-Host "Čekám 3 sekundy..." -ForegroundColor Gray
Start-Sleep -Seconds 3

Write-Host "Spouštím služby..." -ForegroundColor Cyan
& "$root\04_scripts\start-all.ps1"
