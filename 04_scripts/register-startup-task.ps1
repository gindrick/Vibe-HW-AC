# Registruje Windows Task Scheduler úlohu pro automatický start JJA služeb
# Úloha běží při startu systému — bez nutnosti přihlášeného uživatele.
#
# SPUSTIT JAKO ADMINISTRÁTOR!
# Použití: klikněte pravým tlačítkem na PowerShell → "Spustit jako správce"
#          cd c:\jja && .\04_scripts\register-startup-task.ps1

$taskName   = "JJA-StartAll"
$scriptPath = "C:\jja\04_scripts\start-all.ps1"

Write-Host "Registruji Task Scheduler úlohu '$taskName'..."
Write-Host ""

# Akce: spustí start-all.ps1 přes PowerShell bez okna
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -NoProfile -WindowStyle Hidden -File `"$scriptPath`"" `
    -WorkingDirectory "C:\jja"

# Trigger: při startu systému (nezávisí na přihlášení uživatele)
$trigger = New-ScheduledTaskTrigger -AtStartup

# Nastavení: bez časového omezení, spustit i když uživatel není přihlášen
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

# Principal: aktuální uživatel s S4U logon — běží i bez přihlášení,
# stejné prostředí (ODBC drivery, env vars) jako interaktivní uživatel,
# nevyžaduje uložení hesla.
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "Uživatel pro task: $currentUser"

$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType S4U `
    -RunLevel Highest

try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Spustí všechny JJA služby (LiteLLM, router, hr_hiring backend+frontend, ...) při startu systému" `
        -Force

    Write-Host "OK: Úloha '$taskName' úspěšně zaregistrována." -ForegroundColor Green
    Write-Host "    Spustí se automaticky při příštím startu Windows."
    Write-Host ""
    Write-Host "Pro okamžité spuštění bez restartu:"
    Write-Host "    schtasks /run /tn $taskName"
    Write-Host ""
    Write-Host "Logy služeb: C:\jja\logs\"
} catch {
    Write-Error "Chyba při registraci: $_"
    Write-Host ""
    Write-Host "Ujistěte se, že PowerShell běží jako Administrátor!" -ForegroundColor Yellow
}
