# 📚 Agenda UNOESC

![CI](https://github.com/SEU_USUARIO/unoesc-agenda-project/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue)

Aplicação web que automatiza a busca de atividades acadêmicas (webconferências, prazos de entrega, provas, etc.) no portal do aluno da UNOESC e as sincroniza com o Google Calendar.

- **Login automático** no portal acadêmico via Playwright
- **SSO automático** para o Moodle e leitura do calendário consolidado
- **Detecção de webconferências** no texto de cada disciplina via Google Gemini
- **Cache local** em SQLite — abre sem refazer scraping
- **Marcar como concluído**, **alertas de eventos próximos** e **link direto** pra cada atividade no portal
- **Sincronização com Google Calendar** via popup OAuth (sem secrets no servidor)

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
- Conta no **Google AI Studio** (chave da Gemini API — gratuita)
- Conta no **Google Cloud Console** (Client ID OAuth do Google Calendar — gratuita)
- Credenciais do **portal UNOESC** (matrícula/CPF + senha)

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
- Baixa o Chromium do Playwright
- Instala dependências do frontend (`npm install`)
- Copia os arquivos `.env.example` para `.env`

### 3. Configure as chaves de API

Você precisa preencher **2 arquivos `.env`** com chaves do Google:
- `backend/.env` — chave do **Gemini** (uma só)
- `frontend/.env` — **Client ID OAuth** do Google Calendar

As próximas duas seções mostram como obter cada uma. **Faça as duas antes de rodar o app.**

---

## 🔑 Configurando o Gemini (extração de eventos por IA)

A Gemini API é usada para encontrar webconferências no texto das disciplinas. Tem **free tier generoso** (15 requisições/minuto, 1500/dia) — não precisa cartão de crédito.

1. Acesse [https://aistudio.google.com/](https://aistudio.google.com/) e faça login com sua conta Google.
2. Clique em **"Get API key"** (canto superior esquerdo) → **"Create API key"**.
3. Copie a chave gerada (algo como `AIzaSy...`).
4. Abra `backend/.env` e cole:

   ```
   GEMINI_API_KEY=AIzaSy...sua_chave_aqui
   ```

5. **Importante**: pode ser que precise habilitar a Gemini API explicitamente na primeira vez. Se ao testar o app você receber erro `SERVICE_DISABLED`, abra o link que aparece na mensagem (algo como `https://console.developers.google.com/apis/api/generativelanguage.googleapis.com/overview?project=ID_DO_PROJETO`) e clique em **"Ativar"**.

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
   - Em **"Origens JavaScript autorizadas"** adicione **as duas URLs** abaixo (o Vite alterna entre elas se uma estiver ocupada):
     ```
     http://localhost:5173
     http://localhost:5174
     ```
6. Copie o **Client ID** gerado e cole em `frontend/.env`:

   ```
   VITE_GOOGLE_CLIENT_ID=000000000000-xxxxxxxxxxxx.apps.googleusercontent.com
   ```

> ℹ️ Se tiver mais de uma pessoa usando, você pode reusar **o mesmo Client ID** entre todos — basta adicionar cada e-mail como Test user da tela de consentimento.

---

## ▶️ Rodando a aplicação

Você precisa de **dois terminais** abertos (um pro backend, um pro frontend):

### Terminal 1 — Backend (FastAPI)

**Windows:**

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

**Linux / macOS:**

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

API disponível em **http://localhost:8000** · Docs Swagger em **http://localhost:8000/docs**

### Terminal 2 — Frontend (Vite)

```bash
cd frontend
npm run dev
```

Abre em **http://localhost:5173** (ou 5174 se a 5173 estiver ocupada).

### Como usar

1. Acesse `http://localhost:5173` no navegador.
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
| `GEMINI_API_KEY` | **Sim** | Chave da Gemini API. [Como obter](#-configurando-o-gemini-extração-de-eventos-por-ia). |
| `GEMINI_MODEL` | Não | Modelo Gemini. Padrão: `gemini-2.5-flash`. |

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
│   │   ├── scraper.py           # Playwright: login + Moodle + calendário
│   │   ├── parser.py            # Gemini: extração de webconferências
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

Para resetar o banco: apague o arquivo `backend/agenda.db` e faça login novamente.

---

## 🐛 Troubleshooting

### `ModuleNotFoundError: No module named 'X'`
Você esqueceu de ativar o `venv` ou de rodar `pip install -r requirements.txt`. O `setup.ps1`/`setup.sh` faz isso por você.

### `NotImplementedError` ao fazer scraping (Windows)
Já tratado no código (Playwright sync mode). Se ainda assim aparecer, rode com `python -m uvicorn app.main:app` em vez de `uvicorn` direto.

### Erro `SERVICE_DISABLED` ao usar a IA
A Gemini API ainda não foi habilitada no seu projeto Google. A mensagem de erro contém um link `https://console.developers.google.com/apis/...` — abra ele e clique em **"Ativar"**. Espere 1-2 minutos.

### Botão "Sincronizar com Google Calendar" não funciona
- Verifique se o `VITE_GOOGLE_CLIENT_ID` está em `frontend/.env` (não em `.env.example`!).
- Reinicie o `npm run dev` depois de criar/editar o `.env` (Vite só lê na inicialização).
- Confirme que `http://localhost:5173` (e 5174) estão em **Origens JavaScript autorizadas** no Google Cloud Console.
- Confirme que seu e-mail Google está adicionado como **Test user** na Tela de Consentimento OAuth.

### Login no portal UNOESC falha
- Confirme as credenciais fazendo login direto em https://acad.unoesc.edu.br
- Use sua matrícula (números) ou CPF + senha de acesso ao portal

### "Não vem nada" ao atualizar uma disciplina
Algumas disciplinas só têm conteúdo após a data de início (ex: começam em maio). Se o Moodle mostrar *"O acesso ao componente curricular ainda não está disponível"*, é normal o app capturar pouco conteúdo dela.

### O `tsc` reclama de algum tipo
Reinstale as deps do frontend: `cd frontend && rm -rf node_modules && npm install`.

### Banner "Sem conexão com o servidor"
O backend (uvicorn) está parado ou caiu. Sobe ele de novo no terminal do backend e o banner some automaticamente.

### Quero começar do zero (apagar cache)
Na tela do grid de disciplinas, clique em **"Limpar cache"** no canto superior direito. Subjects e eventos são apagados; eventos marcados como concluídos são preservados. Depois faça login para refazer o scraping.

Para apagar **tudo** (incluindo concluídos), apague o arquivo `backend/agenda.db`.

---

## 🛠️ Stack

| Camada | Tecnologia |
| --- | --- |
| Scraping + login | Python + Playwright (sync API) |
| Calendário consolidado | Moodle `view.php?view=upcoming` (HTML estruturado) |
| Detecção de webconferências | Google Gemini 2.5 Flash |
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
