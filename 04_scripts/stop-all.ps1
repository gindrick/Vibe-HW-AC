# Zastaví všechny běžící Python a Node procesy spuštěné touto sadou
# Použití: ./scripts/stop-all.ps1

Write-Host "Zastavuji Python procesy..."
Get-Process -Name python, pythonw -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "Zastavuji Node procesy..."
Get-Process -Name node -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "Hotovo."
