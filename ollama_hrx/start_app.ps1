# Spuštění Ollama na pozadí (pokud již neběží)
$ollamaProcess = Get-Process ollama -ErrorAction SilentlyContinue
if (-not $ollamaProcess) {
    Write-Host "Spouštění Ollama..."
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5  # Počkat, až se Ollama spustí
}

# Spuštění FastAPI aplikace
Write-Host "Spouštění FastAPI aplikace..."
cd c:\jja\ollama_hrx
$env:LLM_PROVIDER="ollama"
C:\jja\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
