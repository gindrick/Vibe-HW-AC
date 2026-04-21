# Zobrazí stav všech JJA služeb
# Použití: cd c:/jja && ./04_scripts/status.ps1

$services = @(
    @{ Name = "01-mcp";             Port = 8002; Desc = "MCP server" }
    @{ Name = "02-litellm";         Port = 4000; Desc = "LiteLLM proxy" }
    @{ Name = "03-router";          Port = 8000; Desc = "Router (vstupní bod)" }
    @{ Name = "react-assistant";    Port = 8001; Desc = "React Assistant web UI" }
    @{ Name = "hr-demo";            Port = 8003; Desc = "HR Demo" }
    @{ Name = "hr-hiring-backend";  Port = 8010; Desc = "HR Hiring backend" }
    @{ Name = "hr-hiring-frontend";          Port = 5173; Desc = "HR Hiring frontend (Vite)" }
    @{ Name = "production-cards-backend";    Port = 8011; Desc = "Production Cards backend" }
    @{ Name = "production-cards-frontend";   Port = 5174; Desc = "Production Cards frontend" }
)

# Načteme všechna naslouchající spojení jednou
$listening = netstat -ano | Select-String 'LISTENING'

Write-Host ""
Write-Host "JJA – stav služeb" -ForegroundColor Cyan
Write-Host ("=" * 55) -ForegroundColor Cyan
Write-Host ""

$allOk = $true

foreach ($svc in $services) {
    $port   = $svc.Port
    $match  = $listening | Where-Object { $_ -match ":$port\s" }

    if ($match) {
        # Extrahuj PID z posledního sloupce
        $pid_val = ($match | Select-Object -First 1) -replace '.*\s+(\d+)\s*$', '$1'
        try {
            $proc = Get-Process -Id ([int]$pid_val.Trim()) -ErrorAction SilentlyContinue
            $procName = if ($proc) { $proc.ProcessName } else { "?" }
            $uptime   = if ($proc -and $proc.StartTime) {
                $diff = (Get-Date) - $proc.StartTime
                if ($diff.TotalHours -ge 1) { "{0}h {1}m" -f [int]$diff.TotalHours, $diff.Minutes }
                else { "{0}m" -f $diff.Minutes }
            } else { "" }
        } catch { $procName = "?"; $uptime = "" }

        $uptimeStr = if ($uptime) { "  (nahoru $uptime)" } else { "" }
        Write-Host ("  [OK] :{0,-5}  {1,-24} {2}{3}" -f $port, $svc.Desc, $svc.Name, $uptimeStr) -ForegroundColor Green
    } else {
        Write-Host ("  [!!] :{0,-5}  {1,-24} {2}  <- NEBĚŽÍ" -f $port, $svc.Desc, $svc.Name) -ForegroundColor Red
        $allOk = $false
    }
}

Write-Host ""
if ($allOk) {
    Write-Host "Všechny služby běží." -ForegroundColor Green
} else {
    Write-Host "Některé služby neběží. Spusť: .\04_scripts\start-all.ps1" -ForegroundColor Yellow
}
Write-Host ""
