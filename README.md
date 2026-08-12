# 📚 Agenda UNOESC

![CI](https://github.com/SEU_USUARIO/unoesc-agenda-project/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue)

Aplicação web que reúne as atividades acadêmicas (prazos de entrega, provas, webconferências) de todas as disciplinas do Moodle da UNOESC numa agenda só.

O aluno entra com a conta do Moodle e vê tudo numa lista. Não instala nada, não configura chave de API, não cria conta.

> Projeto independente, feito por alunos. **Não é um serviço oficial da UNOESC.**

- **Login direto no Moodle** por HTTP — sem navegador headless, sem SSO pelo portal
- **Calendário via API** do Moodle: data, hora, disciplina e link já estruturados
- **Multi-usuário** — cada aluno vê apenas a própria agenda
- **Assistente de organização** (opcional) — prioridades, plano de estudo, acúmulo de prazos
- **Marcar como concluído**, **alertas de eventos próximos** e **link direto** pra cada atividade
- **Deploy único** — um container serve a API e a interface
- **Responsivo** — funciona no celular

---

## 📖 Índice

- [O que o app não faz](#-o-que-o-app-não-faz)
- [Rodando localmente](#-rodando-localmente)
- [Assistente de organização](#-assistente-de-organização)
- [Publicando num domínio](#-publicando-num-domínio)
- [Privacidade e credenciais](#-privacidade-e-credenciais)
- [Variáveis de ambiente](#-variáveis-de-ambiente)
- [Estrutura do projeto](#-estrutura-do-projeto)
- [Testes](#-testes)
- [Troubleshooting](#-troubleshooting)

---

## 🚫 O que o app não faz

O projeto já teve um assistente que baixava o enunciado das atividades e devolvia as respostas de provas. **Isso foi removido** quando ele passou a ser hospedado publicamente: distribuir uma ferramenta dessas sob um domínio próprio esbarra no regulamento acadêmico, e o risco recai sobre quem hospeda.

O que ficou é um assistente que só enxerga **título, data e disciplina** — o suficiente para ajudar a planejar, insuficiente para responder qualquer coisa.

A sincronização com o **Google Calendar** está desligada nesta versão. O código continua no repositório; o que falta é a verificação da tela de consentimento OAuth pelo Google, exigida para escopos sensíveis. Sem `VITE_GOOGLE_CLIENT_ID` configurado, os botões não aparecem.

---

## 🚀 Rodando localmente

### Pré-requisitos

| Ferramenta | Versão mínima |
| --- | --- |
| **Python** | 3.11+ |
| **Node.js** | 18+ |
| **Git** | qualquer |

Você vai precisar das suas credenciais do Moodle (`<matrícula>@unoesc.edu.br` + senha). **Nenhuma chave de API é necessária.**

### 1. Clone e rode o setup

```bash
git clone https://github.com/SEU_USUARIO/unoesc-agenda-project.git
cd unoesc-agenda-project
./setup.sh          # Windows: .\setup.ps1
```

O script cria o `venv`, instala as dependências dos dois lados e copia os `.env.example`.

### 2. Suba os dois serviços

```bash
make dev            # Windows: .\dev.ps1
```

Frontend em **http://localhost:5180** · API em **http://localhost:8880** · Swagger em **/docs**.

### 3. Use

1. Entre com usuário e senha do Moodle.
2. O primeiro acesso lê todas as disciplinas — leva cerca de um minuto.
3. Nas próximas vezes a agenda abre na hora, do cache, e atualiza em segundo plano.
4. Clique num evento para ver detalhes e abrir a atividade no Moodle.
5. Marque o que já entregou como concluído.

---

## 🧠 Assistente de organização

Opcional. Sem chave configurada, o botão não aparece e o resto do app funciona igual.

Ele responde coisas como *"o que eu preciso entregar essa semana?"*, *"monte um plano de estudo até a prova"* ou *"tem algum dia com entregas acumuladas?"*.

**O que ele recebe**: a lista de atividades pendentes — data, hora, disciplina, tipo e título. Nada mais. O prompt em `backend/app/assistant.py` recusa pedidos de resolver questões, mesmo se o aluno colar o enunciado.

### Configurar

No `backend/.env`:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.0-flash
```

Chave gratuita em [aistudio.google.com](https://aistudio.google.com/). Para usar Claude, troque `AI_PROVIDER=claude` e preencha `ANTHROPIC_API_KEY`.

### Cota

Como quem hospeda paga a conta, cada aluno tem um limite mensal — `FREE_AI_QUOTA` (padrão 5) e `PRO_AI_QUOTA` (padrão 200), com o plano gravado na coluna `plan` da tabela `users`. Só metadados vão no contexto, então cada pergunta custa fração de centavo.

> A cobrança em si (gateway de pagamento, nota fiscal) ainda não existe — ver `docs/PLANO_PUBLICO.md`, fase 7.

---

## 🌐 Publicando num domínio

O `Dockerfile` compila o frontend e o serve pelo próprio FastAPI: **um container, um domínio, sem CORS**.

```bash
make docker         # build local
docker run -p 8080:8080 -v agenda-dados:/data \
  -e SESSION_SECRET="$(openssl rand -base64 32)" agenda-unoesc
```

### Fly.io

```bash
fly launch --no-deploy
fly volumes create dados --size 1 --region gru
fly secrets set SESSION_SECRET="$(openssl rand -base64 32)"
fly deploy
```

Ajuste o nome do app em `fly.toml` antes.

> ⚠️ **O volume não é opcional.** O SQLite vive em `/data/agenda.db`; sem volume montado, cada deploy apaga a agenda de todo mundo.

> ⚠️ **Uma instância só.** SQLite exige que todas as requisições cheguem ao mesmo disco. Para crescer além disso, troque por Postgres — não suba réplicas.

### Backup

O banco é um arquivo. Um cron diário copiando `/data/agenda.db` para um bucket resolve; não há réplica.

---

## 🔒 Privacidade e credenciais

Este é o ponto mais sensível do projeto, e vale entender antes de hospedar para outras pessoas.

**A senha do Moodle é guardada, cifrada, no servidor.** O cliente do Moodle precisa relogar sozinho quando a sessão de lá expira — guardar só o cookie obrigaria o aluno a redigitar a senha várias vezes por dia. O raciocínio completo está em `backend/app/crypto.py`.

Isso protege contra vazamento do banco: um dump do SQLite não entrega senha nenhuma sem a `SESSION_SECRET`, que fica nas variáveis de ambiente. **Não** protege contra comprometimento do servidor rodando — quem tem o processo tem a chave e o banco juntos.

A solução real é o Moodle emitir um token de web service por aluno, o que tiraria a senha do fluxo inteiro. É o item de maior impacto no `docs/PLANO_PUBLICO.md` e depende de conversar com a TI da UNOESC.

O que já está no código:

- Token de sessão gravado **hasheado** — ler o banco não permite se passar por um usuário logado
- Sessão expira após 8h de inatividade
- Rate limit no `/api/login` — sem ele, o servidor viraria ferramenta de força bruta contra o Moodle
- Aviso de privacidade **antes** do campo de senha
- Botão **Excluir conta**, que apaga dados, marcações e credenciais

---

## 🔧 Variáveis de ambiente

### `backend/.env`

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `SESSION_SECRET` | Em produção | Cifra as senhas guardadas em sessão. Gere com `openssl rand -base64 32`. Trocar derruba as sessões abertas. |
| `APP_ENV` | Não | `production` torna a `SESSION_SECRET` obrigatória. Padrão: `development`. |
| `DATABASE_PATH` | Não | Caminho do SQLite. Em produção, aponte para o volume persistente. |
| `FRONTEND_DIST` | Não | Pasta do frontend compilado. Se existir, o FastAPI serve a interface no mesmo domínio. |
| `ALLOWED_ORIGINS` | Não | Origens do CORS, separadas por vírgula. Vazio = padrão de desenvolvimento (Vite em `localhost:51xx`). |
| `AI_PROVIDER` | Não | `gemini` (padrão) ou `claude`. |
| `GEMINI_API_KEY` | Não | Só para o assistente de organização. |
| `ANTHROPIC_API_KEY` | Se `AI_PROVIDER=claude` | Idem. |
| `FREE_AI_QUOTA` / `PRO_AI_QUOTA` | Não | Perguntas por mês em cada plano. Padrão: 5 e 200. |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_WINDOW_MINUTES` | Não | Rate limit do login. Padrão: 5 tentativas / 15 min. |

### `frontend/.env`

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `VITE_GOOGLE_CLIENT_ID` | Não | Deixe vazio: com o Google Calendar desligado, os botões de sincronizar não aparecem. |

---

## 📁 Estrutura do projeto

```
unoesc-agenda-project/
├── Dockerfile                   # frontend compilado + API num container só
├── fly.toml                     # deploy no Fly.io (volume obrigatório)
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI: endpoints REST + entrega do frontend
│   │   ├── moodle.py            # Cliente HTTP do Moodle: login + disciplinas + calendário
│   │   ├── database.py          # SQLAlchemy + modelos (todos com user_id)
│   │   ├── repository.py        # CRUD/upsert do cache, sempre filtrado por aluno
│   │   ├── session.py           # Sessões em banco, token hasheado
│   │   ├── crypto.py            # Cifragem das senhas guardadas
│   │   ├── ratelimit.py         # Proteção do /api/login
│   │   ├── assistant.py         # Assistente de organização + cota
│   │   └── calendar_sync.py     # Google Calendar (desligado na v1)
│   ├── tests/
│   │   └── test_isolamento.py   # Critério de aceite do multi-tenant
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── LoginForm.tsx         # Login + aviso de privacidade
│   │   │   ├── SubjectList.tsx       # Grid de disciplinas
│   │   │   ├── SubjectDetail.tsx     # Eventos de uma disciplina
│   │   │   ├── EventModal.tsx        # Modal de detalhes
│   │   │   ├── EventAlerts.tsx       # Banner de alertas urgentes
│   │   │   └── Assistant.tsx         # Chat de organização
│   │   ├── contexts/DoneEventsContext.tsx
│   │   ├── services/api.ts
│   │   └── App.tsx
│   └── package.json
└── docs/
    ├── SETUP.md
    └── PLANO_PUBLICO.md         # Plano da versão pública, por fases
```

---

## 🗃️ Banco (SQLite)

Criado automaticamente no primeiro login. Tabelas:

- `users` — um por aluno, criado no primeiro login bem-sucedido no Moodle
- `sessions` — token hasheado + senha cifrada, com TTL de 8h
- `subjects` / `events` / `done_events` / `meta` — cache por aluno, PK composta com `user_id`

Eventos antigos **não** são removidos quando o scrape roda de novo — preserva histórico mesmo depois que somem do calendário do Moodle.

> Um banco vindo da versão single-user é detectado no startup e as tabelas de cache são recriadas com `user_id`. Tudo se reconstrói no próximo login; a única perda são as marcações de "concluído" antigas.

Para resetar:

```bash
make clean
```

---

## 🧪 Testes

```bash
make test
```

Roda `backend/tests/test_isolamento.py` contra um Moodle falso, sem rede. Verifica que dois alunos logados ao mesmo tempo não enxergam nada um do outro, que nenhum endpoint de dados responde sem sessão, que o rate limit do login funciona e que excluir a conta apaga tudo.

É o critério de aceite da versão pública — roda no CI a cada push.

---

## 🐛 Troubleshooting

### Login no Moodle falha
Use a matrícula no formato `294833@unoesc.edu.br` (com o domínio). Confirme que consegue entrar em https://on.unoesc.edu.br pelo navegador.

### "Muitas tentativas de login"
O rate limit bloqueou após 5 tentativas erradas. Espere 15 minutos ou ajuste `LOGIN_MAX_ATTEMPTS`.

### Todo mundo é deslogado a cada deploy
Falta `SESSION_SECRET` fixa. Sem ela o backend gera uma chave efêmera a cada boot, e as senhas cifradas com a chave antiga não são mais legíveis.

### A agenda some depois do deploy
O volume não está montado. Confirme que `DATABASE_PATH` aponta para dentro dele.

### "Não vem nada" numa disciplina
Algumas só têm conteúdo após a data de início. Se o Moodle mostra *"O acesso ao componente curricular ainda não está disponível"*, é normal.

### Agenda vazia mesmo com disciplinas
Curso presencial normalmente não usa `assign`/`quiz` no Moodle, e sem isso não há o que listar no calendário. O app serve bem quem faz EAD.

### Venv criado no Windows não funciona no WSL
```bash
rm -rf backend/.venv && ./setup.sh
```

### Banner "Sem conexão com o servidor"
O backend está parado. Suba de novo e o banner some sozinho.

---

## 🛠️ Stack

| Camada | Tecnologia |
| --- | --- |
| Acesso ao Moodle | Python + httpx (login HTTP + API AJAX interna) |
| Calendário | `core_calendar_get_calendar_monthly_view` (JSON) |
| Backend API | FastAPI + Uvicorn |
| Persistência | SQLite + SQLAlchemy 2.x |
| Cifragem | `cryptography` (Fernet) |
| Frontend | React 18 + TypeScript + Vite |
| Deploy | Docker (multi-stage) + Fly.io |

---

## 🤝 Contribuindo

Pull requests são bem-vindos. Para mudanças grandes, abra uma *issue* primeiro.

Qualquer mudança em `repository.py` precisa passar por `make test` — é o que garante que um aluno não vê os dados de outro.

---

## 📄 Licença

[MIT](LICENSE)
