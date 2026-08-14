# Agenda UNOESC — contexto do projeto

App que reúne prazos, provas e webconferências de todas as disciplinas do Moodle
da UNOESC numa agenda só. FastAPI + SQLite no backend, React + TypeScript + Vite
no frontend, tudo num container só no Fly.io (`unoesc-agenda.fly.dev`).

Projeto independente feito por alunos — **não é serviço oficial da UNOESC**, e
isso precisa continuar visível na interface.

## Comandos

```bash
make dev      # backend em :8880 + frontend em :5180
make test     # teste de isolamento multi-tenant (critério de aceite)
make deploy   # backup do banco de produção + test + fly deploy
```

Frontend: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`.

## Decisões que não são óbvias no código

**A senha do Moodle é guardada cifrada no servidor.** Não é descuido: o cliente
precisa relogar sozinho quando a sessão do Moodle expira. O raciocínio inteiro
está em `backend/app/crypto.py`. Substituir isso por token de web service é o
item de maior impacto do `docs/PLANO_PUBLICO.md`.

**O enunciado da atividade é lido, mas só para a tela.** `activity_content()` já
foi apagado uma vez, porque alimentava um assistente que respondia provas.
Voltou em 14/08/2026 com destino único: a página da atividade. `assistant.py`
monta o contexto com data, disciplina e título, e só. Não passe o enunciado para
ele.

**A agenda não abre com o cache.** Espera o Moodle responder mostrando só o
esqueleto. Meia agenda velha, numa tela de prazos, é pior que nenhuma — o aluno
não tem como saber qual metade está velha. O cache só entra se o Moodle estiver
fora, e a tela avisa.

**Login automático no Moodle é impossível.** O navegador não aceita cookie de
outro domínio; a única saída seria um plugin instalado pelo admin da UNOESC. Não
tente de novo.

**O app só serve curso EAD.** Curso presencial não gera `assign`/`quiz` no
Moodle, então a agenda abre vazia para esse público.

## Ao mexer no código

- **Endpoint novo que devolva dado do aluno** entra na lista do
  `backend/tests/test_isolamento.py`. A busca é sempre por `(user_id, ...)`.
- **Rota nova no frontend** depende do `SPAStaticFiles` em `main.py` — sem o
  fallback para o `index.html`, o link direto dá 404 em produção.
- **Ícone novo** entra em `frontend/src/components/Icon.tsx`, nunca como emoji.
- **Sem dependência nova no frontend** sem um bom motivo: o público abre isso no
  4G, e o roteador foi escrito à mão por causa disso.

## Como o Jaime trabalha

- Commite direto na `main`, sem branch e sem PR. **Push é decisão dele** —
  pergunte antes.
- Não refaça a interface inteira de uma vez. Mude uma tela, mostre rodando,
  espere a reação. Um redesign completo já foi construído e revertido.
- Ele testa em produção com a própria conta do Moodle; é o único ambiente onde
  dá para ver a agenda com dados reais.
