#!/usr/bin/env bash
# Agenda UNOESC — sobe backend + frontend em paralelo (Linux / WSL / macOS)
#
# Uso:
#   ./dev.sh
#
# Ctrl+C encerra os dois processos.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

if [ ! -f "$ROOT/backend/.venv/bin/activate" ]; then
    echo -e "${RED}✗ backend/.venv (layout Linux) não encontrado.${NC}"
    if [ -f "$ROOT/backend/.venv/Scripts/activate" ]; then
        echo -e "${RED}  O venv atual foi criado no Windows. Apague backend/.venv e rode ./setup.sh dentro do WSL.${NC}"
    else
        echo -e "${RED}  Rode ./setup.sh antes.${NC}"
    fi
    exit 1
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
    echo -e "${RED}✗ frontend/node_modules não encontrado. Rode ./setup.sh antes.${NC}"
    exit 1
fi

PIDS=()

cleanup() {
    echo -e "\n${CYAN}▶ Encerrando processos...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo -e "${GREEN}✓ Tudo encerrado.${NC}"
}
trap cleanup INT TERM EXIT

echo -e "${CYAN}▶ Backend  → http://localhost:8880${NC}"
(
    cd "$ROOT/backend"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec uvicorn app.main:app --reload --port 8880
) &
PIDS+=($!)

echo -e "${CYAN}▶ Frontend → http://localhost:5180${NC}"
(
    cd "$ROOT/frontend"
    exec npm run dev
) &
PIDS+=($!)

wait
