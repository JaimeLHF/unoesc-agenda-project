# 📚 Agenda UNOESC

Aplicação web que automatiza a busca de atividades acadêmicas (webconferências, prazos de entrega, provas, etc.) no portal do aluno da UNOESC e as sincroniza diretamente com o Google Calendar.

---

## 📸 Screenshots

> *(Adicionar prints da interface após a primeira execução)*

---

## 🛠️ Stack de Tecnologias

| Componente | Tecnologia |
|---|---|
| Scraping + Login | Python + Playwright |
| Interpretação de texto | Google Gemini API |
| Integração de calendário | Google Calendar API |
| Backend | Python + FastAPI |
| Frontend | React + TypeScript + Vite |
| Comunicação | REST API (JSON) |

---

## 📋 Pré-requisitos

- **Python 3.11+**
- **Node.js 18+** e **npm**
- Navegadores do Playwright (instalados pelo script abaixo)
- Conta Google com acesso à API do Google Calendar
- Chave de API do Google Gemini

---

## ⚙️ Configuração do Backend

```bash
# 1. Entre na pasta do backend
cd backend

# 2. Crie e ative o ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 3. Instale as dependências Python
pip install -r requirements.txt

# 4. Instale os navegadores do Playwright
playwright install chromium

# 5. Configure as variáveis de ambiente
cp .env.example .env
# Edite o arquivo .env com suas chaves de API (veja as seções abaixo)

# 6. Inicie o servidor FastAPI
uvicorn app.main:app --reload --port 8000
```

O backend ficará disponível em: **http://localhost:8000**
Documentação Swagger automática: **http://localhost:8000/docs**

---

## 🖥️ Configuração do Frontend

```bash
# 1. Entre na pasta do frontend
cd frontend

# 2. Instale as dependências Node.js
npm install

# 3. Inicie o servidor de desenvolvimento Vite
npm run dev
```

O frontend ficará disponível em: **http://localhost:5173**

---

## 🔑 Como obter a chave do Google Gemini

1. Acesse [Google AI Studio](https://aistudio.google.com/)
2. Faça login com sua conta Google
3. Clique em **"Get API key"** → **"Create API key"**
4. Copie a chave gerada e adicione-a ao arquivo `.env`:
   ```
   GEMINI_API_KEY=sua_chave_aqui
   ```

---

## 📅 Como configurar a API do Google Calendar

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/)
2. Crie um novo projeto (ex: `unoesc-agenda`)
3. No menu lateral, vá em **"APIs e Serviços"** → **"Biblioteca"**
4. Pesquise e ative a **"Google Calendar API"**
5. Vá em **"APIs e Serviços"** → **"Credenciais"** → **"Criar Credenciais"** → **"ID do cliente OAuth 2.0"**
6. Selecione o tipo **"Aplicativo da Web"**
7. Adicione `http://localhost:8000` como origem e `http://localhost:8000/api/auth/callback` como URI de redirecionamento
8. Copie o **Client ID** e o **Client Secret** para o arquivo `.env`:
   ```
   GOOGLE_CLIENT_ID=seu_client_id_aqui
   GOOGLE_CLIENT_SECRET=seu_client_secret_aqui
   GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/callback
   ```

---

## 🚀 Como usar a aplicação

1. Certifique-se de que o **backend** e o **frontend** estão em execução
2. Abra **http://localhost:5173** no navegador
3. Digite seu **usuário e senha** do portal UNOESC
4. Clique em **"Buscar Atividades"** — a aplicação fará login no portal e extrairá os dados
5. Aguarde a IA (Gemini) identificar e estruturar os eventos
6. Selecione as disciplinas desejadas
7. Clique em **"Sincronizar com Google Calendar"** e autorize o acesso ao seu calendário
8. Pronto! Os eventos aparecerão no seu Google Calendar 🎉

---

## 📁 Estrutura do Projeto

```
unoesc-agenda-project/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI — ponto de entrada da API
│   │   ├── scraper.py           # Login e extração com Playwright
│   │   ├── parser.py            # Interpretação de texto com Gemini
│   │   └── calendar_sync.py     # Integração com Google Calendar
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── LoginForm.tsx
│   │   │   ├── SubjectList.tsx
│   │   │   └── EventList.tsx
│   │   ├── services/
│   │   │   └── api.ts
│   │   ├── types/
│   │   │   └── index.ts
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── .gitignore
└── README.md
```

---

## ⚠️ Notas Importantes

- **Segurança**: Suas credenciais do portal UNOESC são usadas **apenas em memória** durante a sessão de scraping e **nunca são armazenadas** em disco ou banco de dados.
- **Uso pessoal**: Esta aplicação é destinada ao **uso pessoal** do estudante. Respeite os termos de uso do portal UNOESC.
- **Arquivo `.env`**: Nunca compartilhe ou comite seu arquivo `.env`. Ele está incluído no `.gitignore` para sua proteção.
- **Produção**: Em ambiente de produção, utilize sempre HTTPS para proteger as credenciais em trânsito.

---

## 📄 Licença

Este projeto está licenciado sob a **MIT License** — veja o arquivo [LICENSE](LICENSE) para detalhes.
