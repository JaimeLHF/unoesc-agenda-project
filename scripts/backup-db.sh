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

echo "Baixando /data/agenda.db de $APP…"
# `sftp get` acorda a máquina se ela estiver suspensa e copia o arquivo.
fly ssh sftp get /data/agenda.db "$ARQUIVO" -a "$APP"

TAMANHO="$(du -h "$ARQUIVO" | cut -f1)"
echo "✅ $ARQUIVO ($TAMANHO)"

# Guarda os 10 mais recentes. Backup que enche o disco vira o próximo problema.
ls -1t "$DESTINO"/agenda-*.db 2>/dev/null | tail -n +11 | while read -r antigo; do
  echo "removendo backup antigo: $antigo"
  rm -f "$antigo"
done
