# Plano de implementação — versão pública

Documento de trabalho. Objetivo: transformar o app local single-user numa aplicação
web pública, num domínio próprio, usável por alunos que não sabem programar.

> **Status (12/08/2026):** fases 1 a 6 implementadas. Falta a fase 7 (cobrança),
> que depende de decisões fora do código — gateway, MEI, nota fiscal. Falta
> também validar o `Dockerfile` num build real: a máquina de desenvolvimento não
> tem Docker instalado.

## Escopo travado (v1)

| Item | v1 |
| --- | --- |
| Agenda unificada do Moodle | ✅ grátis |
| Marcar concluído / cache | ✅ grátis |
| Google Calendar | ❌ adiado (etapa 2) |
| Assistente que resolve atividades e provas | ❌ removido |
| IA de **organização** (resumo, prioridade, plano de estudo) | ✅ plano pago |
| Cobrança | 🔜 fase 7, depois de ter usuários |

---

## Fase 1 — Multi-tenant (bloqueante) ✅

Hoje o banco não tem noção de usuário. `backend/app/database.py:4` diz isso
explicitamente: *"A aplicação é local/single-user (…) Sem autenticação, sem
multi-tenant."* Se dois alunos logarem na versão hospedada, o segundo sobrescreve
e enxerga a agenda do primeiro. **Nada mais pode ser publicado antes disso.**

1. Criar modelo `User` — `id` (uuid), `moodle_username` (único), `created_at`,
   `plan` (`free` | `pro`), `last_login_at`.

2. Adicionar `user_id` como parte da chave primária em `Subject`, `Event`,
   `DoneEvent` e `Meta` (`backend/app/database.py:53-110`). As PKs viram
   compostas: `(user_id, name)`, `(user_id, stable_key)`, `(user_id, key)`.

3. Propagar `user_id` em toda função de `backend/app/repository.py` — hoje as
   queries são globais.

4. Fechar os endpoints abertos. `/api/cache`, `/api/done-events` (GET/POST/DELETE)
   e `DELETE /api/cache` não exigem sessão hoje (`backend/app/main.py:287-350`) —
   passam a usar `Depends(require_session)` e filtrar pelo usuário do token.

5. Migração: `_run_lightweight_migrations()` só adiciona colunas, não recria PKs.
   Para o deploy novo o caminho é banco limpo — o `agenda.db` local é descartável.

> ⚠️ Critério de aceite: subir duas sessões com contas diferentes e confirmar que
> cada uma só vê os próprios eventos. Sem esse teste passando, não vai pro ar.
>
> Virou `backend/tests/test_isolamento.py`, rodando com um Moodle falso e sem
> rede. `make test` roda; o CI roda a cada push.

---

## Fase 2 — Sessão que sobrevive a restart ✅

`backend/app/session.py:39` guarda tudo num `dict` de processo: cada deploy
desloga todo mundo, e com duas instâncias metade das requisições falha.

1. Criar tabela `sessions` — `token_hash` (sha256 do token, nunca o token puro),
   `user_id`, `created_at`, `last_used_at`. Mesmo TTL de 8h por inatividade.

2. A senha do Moodle precisa continuar acessível para o relogin automático
   (`MoodleClient` reloga sozinho quando a sessão do portal cai). Guardar
   criptografada com Fernet, chave em `SESSION_SECRET` (variável de ambiente,
   fora do repositório).

3. Trade-off aceito e documentado: quem tiver acesso ao servidor **e** à
   `SESSION_SECRET` consegue ler as senhas. A alternativa (guardar só o cookie do
   Moodle) obriga o aluno a redigitar a senha quando a sessão do portal expira.

4. Rate limit em `/api/login` — 5 tentativas por usuário a cada 15 min. Sem isso o
   seu servidor vira ferramenta de força bruta contra a UNOESC e o IP dele leva
   bloqueio.

---

## Fase 3 — Remover a parte de resolver atividade ✅

1. Deletar `POST /api/ai-help` e `POST /api/activity-content`
   (`backend/app/main.py:447` e `:489`) — o segundo é o que baixa o enunciado
   completo da atividade.

2. Deletar `frontend/src/components/AiHelper.tsx` e o botão "🤖 Pedir ajuda à IA"
   do `EventModal.tsx`, incluindo o fluxo de "📝 Respostas".

3. Limpar a seção do assistente no `README.md` e no `docs/SETUP.md`.

4. Remover `ANTHROPIC_API_KEY` / `AI_PROVIDER` do `.env.example`.

---

## Fase 4 — Deploy num domínio ✅

Recomendação: **um serviço só**. O FastAPI serve o `frontend/dist` via
`StaticFiles`. Um deploy, um domínio, sem CORS, sem dois painéis pra administrar.

1. `Dockerfile` no backend — build do frontend em stage 1 (`node`), copia o
   `dist` para o stage 2 (`python`), roda `uvicorn`.

2. Montar `StaticFiles` no `/` do FastAPI, mantendo as rotas sob `/api`.

3. Trocar o CORS fixo de localhost (`backend/app/main.py:127`) por
   `ALLOWED_ORIGINS` lida do ambiente. Com deploy único, some quase inteiro.

4. Hospedar no Fly.io ou Railway, com **volume persistente** montado onde fica o
   `agenda.db` — sem volume, o banco some a cada deploy.

5. Domínio + HTTPS automático. Custo total: ~US$5/mês de servidor + ~R$40/ano de
   domínio.

6. Backup: cron diário copiando o `agenda.db` pra um bucket. SQLite em volume
   único não tem réplica.

---

## Fase 5 — Onboarding pra quem não é técnico ✅

1. Landing de uma tela: o que o app faz, um print, botão "Entrar com minha conta
   da UNOESC".

2. Login pede só matrícula e senha. Nenhuma chave de API, nenhum arquivo `.env`,
   nenhuma configuração.

3. Primeiro scrape dispara automático logo após o login, com barra de progresso —
   hoje o `/api/scrape` é manual.

4. Aviso de privacidade **antes** do campo de senha: o que é guardado, por quê, e
   como apagar a conta.

5. Botão "Excluir minha conta e meus dados", que apaga usuário, eventos e
   credenciais. Exigência prática de LGPD.

---

## Fase 6 — IA de organização ✅

Só metadados que já estão no cache: título, data, disciplina, tipo.

> **Atualização de 14/08/2026.** O app voltou a ler o conteúdo da atividade, mas
> só para mostrar na página dela (`MoodleClient.activity_content`, usada pelo
> `GET /api/activity/<chave>`). O contexto do assistente continua sendo montado
> em `assistant.py` apenas com data, disciplina e título — o enunciado não entra
> nele. Ler para o aluno e responder por ele são coisas diferentes; a fase 5
> removeu a segunda, e ela não volta.

1. `POST /api/assistant` — recebe a pergunta e monta o contexto a partir dos
   eventos do usuário no banco.

2. Casos de uso: resumo da semana, plano de estudo até o prazo, alerta de acúmulo
   de entregas no mesmo dia.

3. Ordenação por prazo e prioridade simples resolve sem LLM — fazer em código, é
   mais rápido e não custa nada.

4. Cota por usuário/mês, gravada no banco. Gemini Flash: fração de centavo por
   chamada, mas cota evita surpresa.

---

## Fase 7 — Cobrança (só depois de ter uso real) ⬜

1. Mercado Pago ou Stripe, assinatura recorrente. Coluna `plan` no `User` +
   webhook para ativar/desativar.

2. Formalizar: MEI, nota fiscal, política de reembolso, termos de uso.

3. Peso jurídico aumenta — você passa a guardar senha do Moodle de **clientes**,
   não de colegas. Vale conversar com a UNOESC antes e pedir um token oficial de
   web service, que eliminaria a senha do fluxo inteiro.

---

## Ordem de execução

```
Fase 1 (multi-tenant)  →  Fase 2 (sessão)  →  Fase 3 (remover IA de prova)
      →  Fase 4 (deploy)  →  Fase 5 (onboarding)  →  público
      →  Fase 6 (IA organização)  →  Fase 7 (cobrança)
```

As fases 1 a 5 são o mínimo pra abrir pro público. 6 e 7 vêm depois, com usuários
reais já usando.

---

## O que falta antes de abrir de verdade

1. **Validar a imagem Docker.** Rodar `make docker` numa máquina com Docker e
   subir o container uma vez. Nada disso foi exercitado ainda.

2. **Provisionar o Fly.io**: criar o app, o volume e a `SESSION_SECRET`. Sem o
   volume, o primeiro deploy já apaga a agenda de todo mundo.

3. **Testar com uma conta real** do Moodle na URL pública, ponta a ponta.

4. **Conversar com a UNOESC.** Pedir um token de web service por aluno é o que
   tira a senha do fluxo — o item de maior impacto do projeto inteiro, e o único
   que não depende de código.
