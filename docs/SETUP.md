# 🛠️ Guia de configuração

Este guia complementa o [README](../README.md) com o passo a passo detalhado de cada etapa. Se você seguir do início ao fim, vai ter o app rodando do zero.

> **Antes de começar**, certifique-se de ter [Python 3.11+](https://python.org), [Node.js 18+](https://nodejs.org) e [Git](https://git-scm.com) instalados.

---

## 1. Clone e setup inicial

```bash
git clone https://github.com/SEU_USUARIO/unoesc-agenda-project.git
cd unoesc-agenda-project
```

**Windows (PowerShell):**

```powershell
.\setup.ps1
```

**Linux / macOS / WSL:**

```bash
make setup
# ou diretamente: chmod +x setup.sh && ./setup.sh
```

O script cria o `venv`, instala as dependências, baixa o Chromium do Playwright e cria os arquivos `.env`. Aguarde até ver "Setup concluído!".

> ⚠️ **WSL**: se você já rodou `.\setup.ps1` no Windows antes, o venv criado não funciona no WSL. Apague com `rm -rf backend/.venv` e rode `./setup.sh` novamente.

---

## 2. Configurando a Gemini API (extração de eventos)

A Gemini API é gratuita (15 req/min, 1500/dia) e não pede cartão de crédito.

### 2.1. Acessar o Google AI Studio

Abra **https://aistudio.google.com/** e faça login com sua conta Google.

### 2.2. Criar a API key

Clique em **"Get API key"** no canto superior esquerdo, depois em **"Create API key"**. Na primeira vez ele cria um projeto Google Cloud por baixo dos panos automaticamente.

### 2.3. Copiar a chave

A chave gerada começa com `AIzaSy...`. **Copie e guarde com cuidado** — quem tiver ela usa sua cota.

### 2.4. Colar em `backend/.env`

Abra `backend/.env` no editor e preencha:

```
GEMINI_API_KEY=AIzaSy...sua_chave_aqui
GEMINI_MODEL=gemini-2.5-flash
```

Salve o arquivo.

### 2.5. Se aparecer erro `SERVICE_DISABLED`

Na primeira execução, pode ser que precise habilitar a API explicitamente. O erro mostra um link tipo `https://console.developers.google.com/apis/api/generativelanguage.googleapis.com/overview?project=ID`. Abra e clique em **"Ativar"**. Espere 1-2 minutos.

### 2.6. E se eu não configurar o Gemini?

A aplicação funciona **parcialmente** sem a chave do Gemini:

| O que funciona | O que NÃO funciona |
| --- | --- |
| Eventos do **calendário do Moodle** (prazos, provas, entregas) — dados estruturados extraídos direto do HTML | **Webconferências** e eventos mencionados apenas no corpo de texto das disciplinas — dependem da IA para serem identificados |

Ou seja: se você só precisa ver prazos e datas de avaliação, pode usar o app normalmente sem Gemini. Mas para ter a visão completa (incluindo encontros síncronos/lives), configure a chave.

---

## 3. Configurando o Assistente de IA (resolver atividades)

O assistente de IA permite resolver atividades e provas diretamente pelo app. Ele suporta dois provedores: **Gemini** (grátis) e **Claude** (pago, melhor qualidade).

### 3.1. Usando Gemini (grátis)

Se você já configurou a `GEMINI_API_KEY` no passo 2, basta garantir que o modelo é o `gemini-2.0-flash` (maior cota gratuita):

```
GEMINI_MODEL=gemini-2.0-flash
AI_PROVIDER=gemini
```

> O `gemini-2.0-flash` tem **1.500 requisições/dia** grátis. O `gemini-2.5-flash` tem apenas 20/dia — evite usá-lo para o assistente.

### 3.2. Usando Claude (pago)

Para melhor qualidade nas respostas:

1. Acesse [console.anthropic.com](https://console.anthropic.com/) e crie uma conta
2. Vá em **Settings → API Keys** → crie uma chave
3. Adicione créditos em **Settings → Billing** (mínimo $5 USD, dura meses com uso normal)
4. No `backend/.env`:

```
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-api03-...sua_chave
CLAUDE_MODEL=claude-haiku-4-5-20251001
```

5. Instale o pacote:
```bash
cd backend
source .venv/bin/activate
pip install anthropic
```

### 3.3. Custos estimados

| Provedor | Modelo | Custo por consulta | Custo mensal estimado |
| --- | --- | --- | --- |
| Gemini | `gemini-2.0-flash` | R$ 0 (grátis até 1500/dia) | R$ 0 |
| Claude | `claude-haiku-4-5-20251001` | ~R$ 0,03 | R$ 5–15 |
| Claude | `claude-sonnet-4-6` | ~R$ 0,15 | R$ 20–50 |

### 3.4. Como trocar de provedor

Altere `AI_PROVIDER` no `backend/.env` e reinicie o backend:

```
AI_PROVIDER=gemini   # ou claude
```

---

## 4. Configurando o Google Calendar (OAuth)

A sincronização com o Google Calendar é feita via popup OAuth no navegador. Você precisa criar um **Client ID** no Google Cloud Console. Não há Client Secret nem redirect URI — fica tudo no frontend.

### 4.1. Criar um novo projeto

Acesse **https://console.cloud.google.com/** e clique no seletor de projeto no topo → **"Novo projeto"**. Nome sugerido: `unoesc-agenda`.

### 4.2. Habilitar a Google Calendar API

No menu lateral, vá em **APIs e Serviços → Biblioteca**, busque por *"Google Calendar API"* e clique em **"Ativar"**.

### 4.3. Configurar a Tela de consentimento OAuth

**APIs e Serviços → Tela de consentimento OAuth**:

- **Tipo de usuário**: Externo
- **Nome do app**: `Agenda UNOESC` (ou o que quiser)
- **E-mail de suporte**: o seu
- **E-mail do desenvolvedor**: o seu

### 4.4. Adicionar Test Users

Na mesma tela de consentimento, role até **"Test users"** e adicione **seu e-mail Google** (e o de qualquer colega que vai usar o app).

> ⚠️ Apenas e-mails listados aqui podem usar a sincronização. Se um colega tentar e não estiver na lista, o popup do Google vai bloquear a autenticação.

### 4.5. Criar o OAuth Client ID

**APIs e Serviços → Credenciais → + Criar credenciais → ID do cliente OAuth 2.0**:

- **Tipo de aplicativo**: Aplicativo da Web
- **Nome**: qualquer um (ex: `Agenda UNOESC Web`)
- **Origens JavaScript autorizadas** (**obrigatório**):
  - `http://localhost:5180`
- **URIs de redirecionamento autorizados**: deixe vazio

> ⚠️ **Atenção**: a origem `http://localhost:5180` **precisa** estar cadastrada aqui. Sem ela, o popup de autenticação do Google será bloqueado e a sincronização com o Calendar não vai funcionar. Se você mudar a porta do Vite, atualize aqui também.

### 4.6. Copiar o Client ID

A janela final mostra o **Client ID** gerado. Copie ele todo (termina com `.apps.googleusercontent.com`).

### 4.7. Colar em `frontend/.env`

```
VITE_GOOGLE_CLIENT_ID=000000000000-xxxxxxxxxxxx.apps.googleusercontent.com
```

Salve o arquivo. Se o `npm run dev` já estava rodando, **reinicie** — o Vite só lê `.env` na inicialização.

---

## 5. Rodando a aplicação

### 5.1. Forma rápida (um comando só)

Sobe backend + frontend em paralelo com um único comando:

**Linux / WSL / macOS:**
```bash
make dev
# ou diretamente: ./dev.sh
```

**Windows (PowerShell):**
```powershell
.\dev.ps1
```

Ctrl+C encerra os dois processos. Você deve ver as URLs:
- Backend: `http://localhost:8880`
- Frontend: `http://localhost:5180`

### 5.2. Forma manual (dois terminais separados)

Se preferir controlar cada processo individualmente:

**Terminal 1 — Backend:**

```bash
cd backend
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uvicorn app.main:app --reload --port 8880
```

**Terminal 2 — Frontend:**

```bash
cd frontend
npm run dev
```

### 5.3. Acessar no navegador

Abra **http://localhost:5180**. Se chegar até a tela de login, está tudo certo.

---

## 6. Solução de problemas comuns

### Venv criado no Windows não funciona no WSL

O `.venv` é específico do sistema operacional. Se você criou pelo Windows e tenta usar no WSL (ou vice-versa), vai dar erro. Solução:

```bash
rm -rf backend/.venv
./setup.sh
```

### Outros problemas

Veja o [README → Troubleshooting](../README.md#-troubleshooting) para erros frequentes.

---

[← Voltar para o README](../README.md)
