# Nejprve spusť router (uvicorn main.py) na pozadí
Write-Host "Starting router..."
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command 'uvicorn main:app --host 0.0.0.0 --port 8000'" -WorkingDirectory "$PSScriptRoot/.."

# Spustí všechny aplikace z apps_start.json podle typu
$appList = Get-Content -Raw -Path "$PSScriptRoot/../apps_start.json" | ConvertFrom-Json
foreach ($app in $appList) {
    Write-Host "Starting $($app.name)..."
    switch ($app.type) {
        "ps1" {
            Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$($app.start)`"" -WorkingDirectory $app.cwd
        }
        "uvicorn" {
            $module = $app.module
            $port = $app.port
            Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command 'uvicorn $module --host 0.0.0.0 --port $port'" -WorkingDirectory $app.cwd
        }
        default {
            Write-Host "Unknown type for $($app.name), skipping."
        }
    }
}
