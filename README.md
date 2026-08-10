# 📚 Agenda UNOESC

![CI](https://github.com/SEU_USUARIO/unoesc-agenda-project/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue)

Aplicação web que reúne as atividades acadêmicas (prazos de entrega, provas, webconferências) de todas as disciplinas do Moodle da UNOESC numa agenda só, e sincroniza com o Google Calendar.

- **Login direto no Moodle** por HTTP — sem navegador headless, sem SSO pelo portal
- **Calendário via API** do Moodle: data, hora, disciplina e link já estruturados
- **Assistente de IA** para resolver atividades e provas (Gemini gratuito ou Claude pago)
- **Respostas de provas** — extrai automaticamente as questões do quiz e retorna as respostas
- **Cache local** em SQLite — abre sem refazer scraping
- **Marcar como concluído**, **alertas de eventos próximos** e **link direto** pra cada atividade no portal
- **Sincronização com Google Calendar** via popup OAuth (sem secrets no servidor)
- **Responsivo** — funciona no celular

---

## 📖 Guia de configuração detalhado

Veja **[docs/SETUP.md](docs/SETUP.md)** para o passo a passo completo de cada etapa (clone, scripts, Gemini API e Google Calendar OAuth).

> _Screenshots e vídeos serão adicionados em breve._

---

## 📋 Pré-requisitos

| Ferramenta | Versão mínima | Como verificar |
| --- | --- | --- |
| **Python** | 3.11+ | `python --version` |
| **Node.js** | 18+ | `node --version` |
| **npm** | 9+ | `npm --version` |
| **Git** | qualquer | `git --version` |

> **Windows**: Python 3.13 e 3.14 funcionam (já testados). No Linux/macOS, qualquer 3.11+ também.

Você também vai precisar:
- Credenciais do **Moodle da UNOESC** (`<matrícula>@unoesc.edu.br` + senha)

Opcionais, só para recursos extras:
- Conta no **Google Cloud Console** — Client ID OAuth, para sincronizar com o Google Calendar
- Chave de **IA** (Gemini ou Claude) — só para o assistente; a agenda funciona sem ela

---

## 🚀 Setup rápido (recomendado)

### 1. Clone o repositório

```bash
git clone https://github.com/SEU_USUARIO/unoesc-agenda-project.git
cd unoesc-agenda-project
```

### 2. Rode o script de setup

**Windows (PowerShell):**

```powershell
.\setup.ps1
```

**Linux / macOS:**

```bash
chmod +x setup.sh
./setup.sh
```

O script faz tudo:
- Cria o `venv` Python e instala dependências
- Instala dependências do frontend (`npm install`)
- Copia os arquivos `.env.example` para `.env`

### 3. Configure as chaves de API

> A agenda já funciona sem configurar chave nenhuma. As chaves abaixo são para os recursos opcionais (Google Calendar e assistente de IA).
- `backend/.env` — chave do **Gemini** (uma só)
- `frontend/.env` — **Client ID OAuth** do Google Calendar

As próximas duas seções mostram como obter cada uma. **Faça as duas antes de rodar o app.**

---

## 🔑 Sobre as chaves de IA

**A agenda funciona sem nenhuma chave de API.** Os eventos vêm estruturados do calendário do Moodle — data, hora, disciplina e link já prontos, sem LLM no caminho.

Antes o app usava o Gemini para garimpar eventos no texto das disciplinas, porque o scraping devolvia HTML solto. Com a API do Moodle isso deixou de ser necessário: `GEMINI_API_KEY` passou de obrigatória a opcional, e serve apenas ao assistente de IA descrito abaixo.

---

## 🤖 Configurando o Assistente de IA

O app possui um **assistente de IA integrado** que ajuda a resolver atividades acadêmicas e provas. Você pode escolher entre dois provedores — basta configurar uma variável no `backend/.env`.

### Comparação de provedores

| | **Gemini (Google)** | **Claude (Anthropic)** |
| --- | --- | --- |
| **Custo** | Gratuito (com limites) | Pago (~R$ 0,03 por consulta no Haiku) |
| **Limite diário** | 1.500 req/dia (gemini-2.0-flash) | Sem limite (enquanto tiver crédito) |
| **Qualidade** | Boa para a maioria das atividades | Excelente, especialmente em questões complexas |
| **Modelo recomendado** | `gemini-2.0-flash` | `claude-haiku-4-5-20251001` (rápido e barato) |
| **Custo mensal estimado** | R$ 0 | R$ 5–15 (uso moderado de estudante) |
| **Precisa de cartão?** | Não | Sim (para adicionar créditos) |

> **Dica**: comece com o Gemini (grátis). Se as respostas não estiverem boas ou a cota estourar, mude para o Claude.

### Opção 1: Gemini (gratuito) — Recomendado para começar

Se você já configurou a Gemini API no passo anterior, o assistente já funciona. Só certifique-se de usar o modelo com mais cota:

```env
GEMINI_API_KEY=AIzaSy...sua_chave
GEMINI_MODEL=gemini-2.0-flash
AI_PROVIDER=gemini
```

> ⚠️ **Não use** `gemini-2.5-flash` para o assistente — ele tem limite de apenas 20 requisições/dia. O `gemini-2.0-flash` tem 1.500 req/dia grátis.

### Opção 2: Claude / Anthropic (pago, melhor qualidade)

1. Acesse [console.anthropic.com](https://console.anthropic.com/) e crie uma conta
2. Vá em **Settings → API Keys** e crie uma nova chave
3. Adicione créditos em **Settings → Billing** (mínimo: $5 USD)
4. No `backend/.env`, adicione:

```env
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-api03-...sua_chave_aqui
CLAUDE_MODEL=claude-haiku-4-5-20251001
```

5. Instale o pacote (necessário apenas na primeira vez ou se não rodou `setup.sh` recentemente):
```bash
cd backend && source .venv/bin/activate && pip install anthropic
```

**Modelos disponíveis do Claude (do mais barato ao mais caro):**

| Modelo | Custo por consulta | Quando usar |
| --- | --- | --- |
| `claude-haiku-4-5-20251001` | ~R$ 0,03 | Quizzes, perguntas objetivas — rápido e barato |
| `claude-sonnet-4-6` | ~R$ 0,15 | Atividades dissertativas, textos complexos |

### Como trocar de provedor

Basta alterar `AI_PROVIDER` no `backend/.env` e reiniciar o backend:

```env
# Para usar Gemini:
AI_PROVIDER=gemini

# Para usar Claude:
AI_PROVIDER=claude
```

### Como usar o assistente

1. Abra qualquer evento e clique em **"🤖 Pedir ajuda à IA"**
2. O sistema acessa o Moodle automaticamente, extrai o conteúdo completo da atividade e abre um chat
3. Pergunte o que quiser — a IA tem acesso ao enunciado, critérios e materiais da atividade
4. **Para provas/quizzes**: clique no botão **"📝 Respostas"**, cole o link da tentativa iniciada no navegador, e receba todas as respostas de uma vez

> ⚠️ **Importante**: para provas, você precisa **iniciar a tentativa no Moodle primeiro** (no seu navegador). Só depois de iniciar, copie a URL (algo como `https://on.unoesc.edu.br/mod/quiz/attempt.php?attempt=123&cmid=456`) e cole no campo que aparece ao clicar "Respostas".

---

## 📅 Configurando o Google Calendar (OAuth)

A sincronização com o Google Calendar acontece **no navegador** via Google Identity Services (popup). Você só precisa de um Client ID — **não há Client Secret nem redirect URI**.

1. Acesse [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um novo projeto (canto superior, *"Selecione um projeto"* → *"Novo projeto"*). Nome: `unoesc-agenda` (ou qualquer um).
3. No menu lateral: **APIs e Serviços** → **Biblioteca** → procure por **"Google Calendar API"** e clique em **"Ativar"**.
4. **APIs e Serviços** → **Tela de consentimento OAuth**:
   - Tipo de usuário: **Externo**
   - Preencha nome do app, e-mail de suporte, e-mail do desenvolvedor
   - Em **"Test users"**, adicione seu e-mail Google (e o de qualquer colega que vai testar)
5. **APIs e Serviços** → **Credenciais** → **+ Criar credenciais** → **ID do cliente OAuth 2.0**:
   - Tipo de aplicativo: **"Aplicativo da Web"**
   - Em **"Origens JavaScript autorizadas"** adicione a URL abaixo (**obrigatório** — sem isso o popup do Google é bloqueado):
     ```
     http://localhost:5180
     ```
6. Copie o **Client ID** gerado e cole em `frontend/.env`:

   ```
   VITE_GOOGLE_CLIENT_ID=000000000000-xxxxxxxxxxxx.apps.googleusercontent.com
   ```

> ℹ️ Se tiver mais de uma pessoa usando, você pode reusar **o mesmo Client ID** entre todos — basta adicionar cada e-mail como Test user da tela de consentimento.

---

## ▶️ Rodando a aplicação

### Forma rápida (recomendada)

Um único comando sobe backend + frontend em paralelo:

**Linux / WSL / macOS:**
```bash
make dev
# ou diretamente: ./dev.sh
```

**Windows (PowerShell):**
```powershell
.\dev.ps1
```

Ctrl+C encerra os dois processos.

> ⚠️ **WSL**: se o venv foi criado no Windows, ele não funciona no WSL. Apague e recrie:
> ```bash
> rm -rf backend/.venv
> ./setup.sh
> ```

### Forma manual (dois terminais)

Se preferir rodar cada serviço separadamente:

**Terminal 1 — Backend (FastAPI):**

```bash
cd backend
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uvicorn app.main:app --reload --port 8880
```

**Terminal 2 — Frontend (Vite):**

```bash
cd frontend
npm run dev
```

API disponível em **http://localhost:8880** · Docs Swagger em **http://localhost:8880/docs**
Frontend em **http://localhost:5180**.

### Como usar

1. Acesse `http://localhost:5180` no navegador.
2. Faça login com seu **usuário (matrícula/CPF) + senha** do portal UNOESC.
3. Aguarde 1-2 minutos enquanto o app:
   - Loga no portal
   - Acessa o Moodle de cada disciplina (SSO)
   - Lê o calendário consolidado
   - Roda o Gemini para webconferências
4. Veja os eventos agrupados por disciplina, ordenados por data.
5. Clique em **um evento** pra abrir o modal com detalhes + link para o portal.
6. **Marque eventos como concluídos** com o checkbox (sincronizado com o banco local).
7. **Sincronize com Google Calendar** clicando no botão dentro de cada disciplina.

---

## 🔧 Variáveis de ambiente

### `backend/.env`

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `GEMINI_API_KEY` | Opcional | Chave da Gemini API. Usada **apenas** pelo assistente de IA (se `AI_PROVIDER=gemini`). A agenda funciona sem ela. |
| `GEMINI_MODEL` | Não | Modelo Gemini. Padrão: `gemini-2.5-flash`. Recomendado: `gemini-2.0-flash` (1500 req/dia grátis). |
| `AI_PROVIDER` | Não | Provedor do assistente de IA: `gemini` (padrão) ou `claude`. |
| `ANTHROPIC_API_KEY` | Apenas se `AI_PROVIDER=claude` | Chave da API Anthropic. [Como obter](https://console.anthropic.com/). |
| `CLAUDE_MODEL` | Não | Modelo Claude. Padrão: `claude-haiku-4-5-20251001`. |

### `frontend/.env`

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `VITE_GOOGLE_CLIENT_ID` | Apenas para sincronizar com Google Calendar | Client ID OAuth. [Como obter](#-configurando-o-google-calendar-oauth). |

---

## 📁 Estrutura do projeto

```
unoesc-agenda-project/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI: endpoints REST
│   │   ├── moodle.py            # Cliente HTTP do Moodle: login + disciplinas + calendário
│   │   ├── calendar_sync.py     # Google Calendar API
│   │   ├── database.py          # SQLAlchemy + modelos SQLite
│   │   └── repository.py        # CRUD/upsert do cache
│   ├── requirements.txt
│   ├── .env.example
│   ├── agenda.db                # SQLite (criado automaticamente, ignorado pelo git)
│   └── .venv/                   # Ambiente virtual Python
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── LoginForm.tsx
│   │   │   ├── SubjectList.tsx       # Grid de disciplinas
│   │   │   ├── SubjectDetail.tsx     # Eventos de uma disciplina
│   │   │   ├── EventModal.tsx        # Modal de detalhes
│   │   │   └── EventAlerts.tsx       # Banner de alertas urgentes
│   │   ├── contexts/
│   │   │   └── DoneEventsContext.tsx # "Concluídos" via API
│   │   ├── services/
│   │   │   ├── api.ts                # Chamadas REST
│   │   │   └── googleAuth.ts         # Google Identity Services
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── .env.example
├── setup.ps1                    # Setup automatizado Windows
├── setup.sh                     # Setup automatizado Linux/macOS
├── .gitignore
└── README.md
```

---

## 🗃️ Banco local (SQLite)

A aplicação usa **SQLite** com SQLAlchemy. O arquivo `backend/agenda.db` é criado automaticamente no primeiro login. Tabelas:

- `subjects` — cache do conteúdo bruto de cada disciplina
- `events` — cache dos eventos extraídos (chave estável `subject|date|title`)
- `done_events` — quais eventos foram marcados como concluídos
- `meta` — metadados livres (ex: timestamp do último scraping)

Eventos antigos **não** são removidos quando o scraper roda de novo — preserva histórico mesmo depois que somem do calendário do Moodle.

Para resetar o banco:
```bash
make clean
# ou manualmente: rm -f backend/agenda.db
```
Depois faça login novamente para recarregar os dados.

---

## 🐛 Troubleshooting

### `ModuleNotFoundError: No module named 'X'`
Você esqueceu de ativar o `venv` ou de rodar `pip install -r requirements.txt`. O `setup.ps1`/`setup.sh` faz isso por você.

### Login no Moodle falha
Use a matrícula no formato `294833@unoesc.edu.br` (com o domínio), e a mesma senha do portal acadêmico. Confirme que consegue entrar em https://on.unoesc.edu.br pelo navegador.

### Erro `SERVICE_DISABLED` ao usar a IA
A Gemini API ainda não foi habilitada no seu projeto Google. A mensagem de erro contém um link `https://console.developers.google.com/apis/...` — abra ele e clique em **"Ativar"**. Espere 1-2 minutos.

### Botão "Sincronizar com Google Calendar" não funciona
- Verifique se o `VITE_GOOGLE_CLIENT_ID` está em `frontend/.env` (não em `.env.example`!).
- Reinicie o `npm run dev` depois de criar/editar o `.env` (Vite só lê na inicialização).
- Confirme que `http://localhost:5180` está em **Origens JavaScript autorizadas** no Google Cloud Console.
- Confirme que seu e-mail Google está adicionado como **Test user** na Tela de Consentimento OAuth.

### Login no portal UNOESC falha
- Confirme as credenciais fazendo login direto em https://acad.unoesc.edu.br
- Use sua matrícula (números) ou CPF + senha de acesso ao portal

### "Não vem nada" ao atualizar uma disciplina
Algumas disciplinas só têm conteúdo após a data de início (ex: começam em maio). Se o Moodle mostrar *"O acesso ao componente curricular ainda não está disponível"*, é normal o app capturar pouco conteúdo dela.

### O `tsc` reclama de algum tipo
Reinstale as deps do frontend: `cd frontend && rm -rf node_modules && npm install`.

### Venv criado no Windows não funciona no WSL
O `.venv` é específico do sistema operacional. Se você criou pelo Windows (`.venv\Scripts\`) e tenta usar no WSL, vai dar erro. Solução:
```bash
rm -rf backend/.venv
./setup.sh
```

### Banner "Sem conexão com o servidor"
O backend (uvicorn) está parado ou caiu. Sobe ele de novo no terminal do backend e o banner some automaticamente.

### Quero começar do zero (apagar cache)
Na tela do grid de disciplinas, clique em **"Limpar cache"** no canto superior direito. Subjects e eventos são apagados; eventos marcados como concluídos são preservados. Depois faça login para refazer o scraping.

Para apagar **tudo** (incluindo concluídos), apague o arquivo `backend/agenda.db`.

---

## 🛠️ Stack

| Camada | Tecnologia |
| --- | --- |
| Acesso ao Moodle | Python + httpx (login HTTP + API AJAX interna) |
| Calendário | `core_calendar_get_calendar_monthly_view` (JSON) |
| Sincronização | Google Calendar API + Google Identity Services |
| Backend API | FastAPI + Uvicorn |
| Persistência | SQLite + SQLAlchemy 2.x |
| Frontend | React 18 + TypeScript + Vite |

---

## ⚠️ Notas importantes

- **Credenciais UNOESC**: usadas **apenas em memória** durante o scraping. Não são gravadas em disco nem em banco.
- **Uso pessoal**: respeite os termos de uso do portal UNOESC. A aplicação foi pensada para uso individual.
- **Arquivos `.env`**: nunca commite. Já estão no `.gitignore`.
- **Banco local**: `agenda.db` também está no `.gitignore` — cada usuário tem o próprio.

---

## 🤝 Contribuindo

Pull requests são bem-vindos. Para mudanças grandes, abra uma *issue* primeiro pra discutir o que mudar.

---

## 📄 Licença

[MIT](LICENSE)
