# Agenda UNOESC — Setup automatizado (Windows / PowerShell)
#
# Roda da raiz do projeto:
#   .\setup.ps1
#
# Cria venv, instala deps Python + Node, baixa Chromium do Playwright,
# e prepara os arquivos .env (sem preencher chaves — você precisa editar
# manualmente, veja README.md).

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "▶ $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "  ✓ $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "  ⚠ $msg" -ForegroundColor Yellow
}

# ----------------------------------------------------------------------
# Verificações de pré-requisitos
# ----------------------------------------------------------------------

Write-Step "Checando pré-requisitos"

try {
    $pythonVersion = (python --version) 2>&1
    Write-OK "Python encontrado: $pythonVersion"
} catch {
    Write-Host "  ✗ Python não encontrado. Instale Python 3.11+ em https://python.org/" -ForegroundColor Red
    exit 1
}

try {
    $nodeVersion = (node --version) 2>&1
    Write-OK "Node encontrado: $nodeVersion"
} catch {
    Write-Host "  ✗ Node.js não encontrado. Instale Node 18+ em https://nodejs.org/" -ForegroundColor Red
    exit 1
}

# ----------------------------------------------------------------------
# Backend
# ----------------------------------------------------------------------

Write-Step "Configurando backend"

Push-Location backend

if (-not (Test-Path .venv)) {
    Write-Host "  Criando venv Python..." -ForegroundColor Gray
    python -m venv .venv
    Write-OK "venv criado"
} else {
    Write-OK "venv já existe"
}

Write-Host "  Instalando dependências Python (pode demorar 1-2 min)..." -ForegroundColor Gray
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\pip.exe install -r requirements.txt --quiet
Write-OK "dependências instaladas"

Write-Host "  Baixando Chromium do Playwright (~150MB, pode demorar)..." -ForegroundColor Gray
& .\.venv\Scripts\playwright.exe install chromium | Out-Null
Write-OK "Chromium instalado"

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-OK ".env criado a partir do .env.example"
    Write-Warn "Edite backend\.env e adicione sua GEMINI_API_KEY (veja README)"
} else {
    Write-OK ".env já existe"
}

Pop-Location

# ----------------------------------------------------------------------
# Frontend
# ----------------------------------------------------------------------

Write-Step "Configurando frontend"

Push-Location frontend

Write-Host "  Instalando dependências Node..." -ForegroundColor Gray
npm install --silent
Write-OK "dependências instaladas"

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-OK ".env criado a partir do .env.example"
    Write-Warn "Edite frontend\.env e adicione seu VITE_GOOGLE_CLIENT_ID (veja README)"
} else {
    Write-OK ".env já existe"
}

Pop-Location

# ----------------------------------------------------------------------
# Próximos passos
# ----------------------------------------------------------------------

Write-Step "Setup concluído!"
Write-Host ""
Write-Host "Próximos passos:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Edite backend\.env  — preencha GEMINI_API_KEY"
Write-Host "     Obtenha em: https://aistudio.google.com/"
Write-Host ""
Write-Host "  2. Edite frontend\.env — preencha VITE_GOOGLE_CLIENT_ID"
Write-Host "     Obtenha em: https://console.cloud.google.com/"
Write-Host ""
Write-Host "  3. Rode em dois terminais:"
Write-Host ""
Write-Host "     Terminal 1 (backend):" -ForegroundColor Gray
Write-Host "       cd backend"
Write-Host "       .venv\Scripts\activate"
Write-Host "       uvicorn app.main:app --reload --port 8000"
Write-Host ""
Write-Host "     Terminal 2 (frontend):" -ForegroundColor Gray
Write-Host "       cd frontend"
Write-Host "       npm run dev"
Write-Host ""
Write-Host "  4. Abra http://localhost:5173 no navegador"
Write-Host ""
Write-Host "Veja README.md para o passo a passo completo de obter as chaves."
