# Agenda UNOESC — Setup automatizado (Windows / PowerShell)
#
# Roda da raiz do projeto:
#   .\setup.ps1
#
# Cria venv, instala deps Python + Node,
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

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-OK ".env criado a partir do .env.example"
    Write-Ok "nenhuma chave e obrigatoria para rodar local - veja backend\.env.example"
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
    Write-Ok "VITE_GOOGLE_CLIENT_ID fica vazio: o Google Calendar esta desligado na v1"
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
Write-Host "  1. Rode: .\dev.ps1"
Write-Host "     A agenda funciona sem configurar chave nenhuma."
Write-Host ""
Write-Host "  2. Opcional — assistente de organização:"
Write-Host "     preencha GEMINI_API_KEY em backend\.env"
Write-Host "     Obtenha em: https://aistudio.google.com/"
Write-Host ""
Write-Host "  3. Ou rode em dois terminais:"
Write-Host ""
Write-Host "     Terminal 1 (backend):" -ForegroundColor Gray
Write-Host "       cd backend"
Write-Host "       .venv\Scripts\activate"
Write-Host "       uvicorn app.main:app --reload --port 8880"
Write-Host ""
Write-Host "     Terminal 2 (frontend):" -ForegroundColor Gray
Write-Host "       cd frontend"
Write-Host "       npm run dev"
Write-Host ""
Write-Host "  4. Abra http://localhost:5180 no navegador"
Write-Host ""
Write-Host "Veja README.md e docs/SETUP.md para os detalhes."
