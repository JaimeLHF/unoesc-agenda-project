# Agenda UNOESC — atalhos de desenvolvimento

.PHONY: dev setup test clean docker

## Sobe backend + frontend em paralelo
dev:
	./dev.sh

## Roda o setup completo (venv, deps, .env)
setup:
	./setup.sh

## Verifica o isolamento entre alunos — critério de aceite do multi-tenant
test:
	cd backend && .venv/bin/python -m tests.test_isolamento

## Constrói a imagem de produção (frontend compilado + API num container só)
docker:
	docker build -t agenda-unoesc .

## Apaga o banco local (agenda.db) para começar do zero
clean:
	rm -f backend/agenda.db
	@echo "Banco apagado. Faça login para recarregar os dados."
