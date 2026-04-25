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

**Linux / macOS:**

```bash
chmod +x setup.sh && ./setup.sh
```

O script cria o `venv`, instala as dependências, baixa o Chromium do Playwright e cria os arquivos `.env`. Aguarde até ver "Setup concluído!".

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

---

## 3. Configurando o Google Calendar (OAuth)

A sincronização com o Google Calendar é feita via popup OAuth no navegador. Você precisa criar um **Client ID** no Google Cloud Console. Não há Client Secret nem redirect URI — fica tudo no frontend.

### 3.1. Criar um novo projeto

Acesse **https://console.cloud.google.com/** e clique no seletor de projeto no topo → **"Novo projeto"**. Nome sugerido: `unoesc-agenda`.

### 3.2. Habilitar a Google Calendar API

No menu lateral, vá em **APIs e Serviços → Biblioteca**, busque por *"Google Calendar API"* e clique em **"Ativar"**.

### 3.3. Configurar a Tela de consentimento OAuth

**APIs e Serviços → Tela de consentimento OAuth**:

- **Tipo de usuário**: Externo
- **Nome do app**: `Agenda UNOESC` (ou o que quiser)
- **E-mail de suporte**: o seu
- **E-mail do desenvolvedor**: o seu

### 3.4. Adicionar Test Users

Na mesma tela de consentimento, role até **"Test users"** e adicione **seu e-mail Google** (e o de qualquer colega que vai usar o app).

> ⚠️ Apenas e-mails listados aqui podem usar a sincronização. Se um colega tentar e não estiver na lista, o popup do Google vai bloquear a autenticação.

### 3.5. Criar o OAuth Client ID

**APIs e Serviços → Credenciais → + Criar credenciais → ID do cliente OAuth 2.0**:

- **Tipo de aplicativo**: Aplicativo da Web
- **Nome**: qualquer um (ex: `Agenda UNOESC Web`)
- **Origens JavaScript autorizadas** (adicione **as duas**):
  - `http://localhost:5173`
  - `http://localhost:5174`
- **URIs de redirecionamento autorizados**: deixe vazio

### 3.6. Copiar o Client ID

A janela final mostra o **Client ID** gerado. Copie ele todo (termina com `.apps.googleusercontent.com`).

### 3.7. Colar em `frontend/.env`

```
VITE_GOOGLE_CLIENT_ID=000000000000-xxxxxxxxxxxx.apps.googleusercontent.com
```

Salve o arquivo. Se o `npm run dev` já estava rodando, **reinicie** — o Vite só lê `.env` na inicialização.

---

## 4. Rodando a aplicação

### 4.1. Terminal 1 — Backend

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

Você deve ver `Uvicorn running on http://127.0.0.1:8000`.

### 4.2. Terminal 2 — Frontend

```bash
cd frontend
npm run dev
```

Você deve ver `Local: http://localhost:5173/`.

### 4.3. Acessar no navegador

Abra **http://localhost:5173**. Se chegar até a tela de login, está tudo certo. 🎉

---

## 5. Solução de problemas comuns

Veja o [README → Troubleshooting](../README.md#-troubleshooting) para erros frequentes.

---

[← Voltar para o README](../README.md)
