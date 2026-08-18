#!/usr/bin/env bash
# Baixa uma cópia do banco de produção para a máquina local.
#
# Por que existe, se o Fly já tira snapshot do volume: o snapshot é do volume
# inteiro, fica na conta do Fly e vence em 5 dias. Se a conta for perdida, ou se
# a descoberta do problema demorar uma semana, não há de onde restaurar. Este
# script tira o backup do lugar onde o problema aconteceria.
#
#   ./scripts/backup-db.sh                 # salva em ./backups/
#   ./scripts/backup-db.sh /caminho/pasta  # salva onde você quiser
#
# Rode antes de qualquer deploy que mexa no banco.

set -euo pipefail

APP="${FLY_APP:-unoesc-agenda}"
DESTINO="${1:-./backups}"
CARIMBO="$(date +%Y-%m-%d_%H%M)"
ARQUIVO="$DESTINO/agenda-$CARIMBO.db"

mkdir -p "$DESTINO"

# A máquina dorme quando ninguém acessa (`min_machines_running = 0`), e o
# `sftp get` não a acorda — ele falha com "app has no started VMs" e derruba o
# `make deploy` inteiro, que roda o backup antes de subir. Quem acorda é uma
# requisição HTTP comum, pelo proxy do Fly.
DOMINIO="${APP_URL:-https://$APP.fly.dev}"
echo "Acordando $DOMINIO…"
for _ in $(seq 1 10); do
  if curl -sf -o /dev/null --max-time 20 "$DOMINIO/api/health/live"; then
    break
  fi
  sleep 3
done

echo "Baixando /data/agenda.db de $APP…"
fly ssh sftp get /data/agenda.db "$ARQUIVO" -a "$APP"

TAMANHO="$(du -h "$ARQUIVO" | cut -f1)"
echo "✅ $ARQUIVO ($TAMANHO)"

# Guarda os 10 mais recentes. Backup que enche o disco vira o próximo problema.
ls -1t "$DESTINO"/agenda-*.db 2>/dev/null | tail -n +11 | while read -r antigo; do
  echo "removendo backup antigo: $antigo"
  rm -f "$antigo"
done
