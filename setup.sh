#!/usr/bin/env bash
# Agenda UNOESC — Setup automatizado (Linux / macOS)
#
# Roda da raiz do projeto:
#   chmod +x setup.sh && ./setup.sh
#
# Cria venv, instala deps Python + Node, baixa Chromium do Playwright,
# e prepara os arquivos .env (sem preencher chaves — você precisa editar
# manualmente, veja README.md).

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
GRAY='\033[0;37m'
NC='\033[0m'

step()  { echo -e "\n${CYAN}▶ $1${NC}"; }
ok()    { echo -e "  ${GREEN}✓ $1${NC}"; }
warn()  { echo -e "  ${YELLOW}⚠ $1${NC}"; }
fail()  { echo -e "  ${RED}✗ $1${NC}"; exit 1; }

# ----------------------------------------------------------------------
# Pré-requisitos
# ----------------------------------------------------------------------

step "Checando pré-requisitos"

if ! command -v python3 >/dev/null 2>&1; then
    fail "Python 3 não encontrado. Instale Python 3.11+."
fi
ok "Python encontrado: $(python3 --version)"

if ! command -v node >/dev/null 2>&1; then
    fail "Node.js não encontrado. Instale Node 18+."
fi
ok "Node encontrado: $(node --version)"

if ! command -v npm >/dev/null 2>&1; then
    fail "npm não encontrado."
fi

# ----------------------------------------------------------------------
# Backend
# ----------------------------------------------------------------------

step "Configurando backend"

cd backend

if [ ! -d .venv ]; then
    echo -e "  ${GRAY}Criando venv Python...${NC}"
    python3 -m venv .venv
    ok "venv criado"
else
    ok "venv já existe"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo -e "  ${GRAY}Instalando dependências Python (pode demorar 1-2 min)...${NC}"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
ok "dependências instaladas"

echo -e "  ${GRAY}Baixando Chromium do Playwright (~150MB, pode demorar)...${NC}"
playwright install chromium >/dev/null
ok "Chromium instalado"

if [ ! -f .env ]; then
    cp .env.example .env
    ok ".env criado a partir do .env.example"
    warn "Edite backend/.env e adicione sua GEMINI_API_KEY (veja README)"
else
    ok ".env já existe"
fi

deactivate
cd ..

# ----------------------------------------------------------------------
# Frontend
# ----------------------------------------------------------------------

step "Configurando frontend"

cd frontend

echo -e "  ${GRAY}Instalando dependências Node...${NC}"
npm install --silent
ok "dependências instaladas"

if [ ! -f .env ]; then
    cp .env.example .env
    ok ".env criado a partir do .env.example"
    warn "Edite frontend/.env e adicione seu VITE_GOOGLE_CLIENT_ID (veja README)"
else
    ok ".env já existe"
fi

cd ..

# ----------------------------------------------------------------------
# Próximos passos
# ----------------------------------------------------------------------

step "Setup concluído!"
echo
echo "Próximos passos:"
echo
echo "  1. Edite backend/.env  — preencha GEMINI_API_KEY"
echo "     Obtenha em: https://aistudio.google.com/"
echo
echo "  2. Edite frontend/.env — preencha VITE_GOOGLE_CLIENT_ID"
echo "     Obtenha em: https://console.cloud.google.com/"
echo
echo "  3. Rode em dois terminais:"
echo
echo -e "     ${GRAY}Terminal 1 (backend):${NC}"
echo "       cd backend"
echo "       source .venv/bin/activate"
echo "       uvicorn app.main:app --reload --port 8000"
echo
echo -e "     ${GRAY}Terminal 2 (frontend):${NC}"
echo "       cd frontend"
echo "       npm run dev"
echo
echo "  4. Abra http://localhost:5173 no navegador"
echo
echo "Veja README.md para o passo a passo completo de obter as chaves."
