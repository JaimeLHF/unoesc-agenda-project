# Agenda UNOESC — atalhos de desenvolvimento

.PHONY: dev setup clean

## Sobe backend + frontend em paralelo
dev:
	./dev.sh

## Roda o setup completo (venv, deps, playwright, .env)
setup:
	./setup.sh

## Apaga o banco local (agenda.db) para começar do zero
clean:
	rm -f backend/agenda.db
	@echo "Cache limpo. Faça login para recarregar os dados."
