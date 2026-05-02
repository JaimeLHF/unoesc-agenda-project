# Agenda UNOESC - sobe backend + frontend em paralelo (Windows PowerShell)
#
# Uso:
#   .\dev.ps1
#
# Ctrl+C encerra os dois processos.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path "$root\backend\.venv\Scripts\Activate.ps1")) {
    Write-Host "[X] backend\.venv (layout Windows) nao encontrado. Rode .\setup.ps1 antes." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "$root\frontend\node_modules")) {
    Write-Host "[X] frontend\node_modules nao encontrado. Rode .\setup.ps1 antes." -ForegroundColor Red
    exit 1
}

$processes = @()

function Stop-All {
    Write-Host ""
    Write-Host ">> Encerrando processos..." -ForegroundColor Cyan
    foreach ($p in $processes) {
        if ($p -and -not $p.HasExited) {
            try {
                taskkill /PID $p.Id /T /F | Out-Null
            } catch {}
        }
    }
    Write-Host "[OK] Tudo encerrado." -ForegroundColor Green
}

try {
    Write-Host ">> Backend  -> http://localhost:8880" -ForegroundColor Cyan
    $backendCmd = "cd `"$root\backend`"; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8880"
    $processes += Start-Process powershell -ArgumentList "-NoExit","-Command",$backendCmd -PassThru

    Write-Host ">> Frontend -> http://localhost:5180" -ForegroundColor Cyan
    $frontendCmd = "cd `"$root\frontend`"; npm run dev"
    $processes += Start-Process powershell -ArgumentList "-NoExit","-Command",$frontendCmd -PassThru

    Write-Host ""
    Write-Host "Pressione Ctrl+C para encerrar ambos." -ForegroundColor Gray

    while ($true) {
        Start-Sleep -Seconds 1
        foreach ($p in $processes) {
            if ($p.HasExited) {
                $exitedId = $p.Id
                $exitedCode = $p.ExitCode
                Write-Host "[X] Um dos processos saiu (PID $exitedId, exit $exitedCode)." -ForegroundColor Red
                Stop-All
                exit $exitedCode
            }
        }
    }
} finally {
    Stop-All
}
