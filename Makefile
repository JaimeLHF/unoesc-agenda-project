# Agenda UNOESC — atalhos de desenvolvimento

.PHONY: dev setup test clean docker backup deploy

## Sobe backend + frontend em paralelo
dev:
	./dev.sh

## Roda o setup completo (venv, deps, .env)
setup:
	./setup.sh

## Verifica o isolamento entre alunos — critério de aceite do multi-tenant —
## mais as funções puras (nome de disciplina, tipo de evento, parsers), que
## quebram calado quando o Moodle muda de layout

test:
	cd backend && .venv/bin/python -m tests.test_isolamento
	cd backend && .venv/bin/python -m tests.test_schedule_pdf
	cd backend && .venv/bin/python -m tests.test_funcoes_puras

## Constrói a imagem de produção (frontend compilado + API num container só)
docker:
	docker build -t agenda-unoesc .

## Baixa uma cópia do banco de produção para ./backups
backup:
	./scripts/backup-db.sh

## Backup + testes + deploy no Fly.io, nessa ordem
deploy: backup test
	fly deploy

## Apaga o banco local (agenda.db) para começar do zero
clean:
	rm -f backend/agenda.db
	@echo "Banco apagado. Faça login para recarregar os dados."
