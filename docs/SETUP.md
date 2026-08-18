# 🛠️ Guia de configuração

Passo a passo detalhado. Para o resumo, veja o [README](../README.md).

> **A agenda funciona sem configurar chave de API nenhuma.** Os eventos vêm estruturados do calendário do Moodle. As seções 3 e 4 são opcionais.

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
chmod +x setup.sh && ./setup.sh
```

O script cria o `venv` Python, instala as dependências dos dois lados e copia os arquivos `.env.example` para `.env`.

---

## 2. Rodando

### 2.1. Um comando só

```bash
make dev          # ou: ./dev.sh
```

**Windows:**

```powershell
.\dev.ps1
```

`Ctrl+C` encerra os dois processos.

### 2.2. Dois terminais separados

**Terminal 1 — backend:**

```bash
cd backend
source .venv/bin/activate      # Windows: .venv\Scripts\activate
uvicorn app.main:app --reload --port 8880
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

### 2.3. Acessar

Abra **http://localhost:5180** e entre com seu usuário e senha do Moodle (`<matrícula>@unoesc.edu.br`).

O primeiro acesso lê todas as disciplinas e leva cerca de um minuto. Enquanto o Moodle não responde, a tela mostra só o esqueleto de carregamento — inclusive nos acessos seguintes. A agenda **não** abre com o cache atualizando por baixo: numa tela de prazos, meia agenda velha é pior que nenhuma, porque não dá para saber qual metade está velha. O cache só entra se o Moodle estiver fora do ar, e a tela avisa que é a última agenda salva.

---

## 3. Assistente de organização (opcional)

Ajuda a planejar: o que entregar primeiro, como dividir o estudo até o prazo, onde há acúmulo de entregas.

Ele recebe **apenas** título, data e disciplina das atividades pendentes. Não abre atividade no Moodle e recusa pedidos de resolver questões — inclusive quando o aluno cola o enunciado na pergunta.

### 3.1. Gemini (gratuito)

1. Acesse [aistudio.google.com](https://aistudio.google.com/).
2. Faça login com sua conta Google.
3. Clique em **"Get API key"** → **"Create API key"**.
4. Copie a chave (começa com `AIza...`).
5. Cole em `backend/.env`:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...sua_chave
GEMINI_MODEL=gemini-3.6-flash
```

> O `gemini-2.0-flash` foi aposentado pelo Google em 18/08/2026 — a API responde
> 404 pedindo para trocar. O nome atual está acima; confira a cota grátis do modelo
> em aistudio.google.com antes de abrir o app para mais gente.

6. Reinicie o backend.

Se aparecer erro `SERVICE_DISABLED`, a Gemini API ainda não foi habilitada no seu projeto Google. A mensagem traz um link `console.developers.google.com/apis/...` — abra, clique em **Ativar** e espere 1-2 minutos.

### 3.2. Claude (pago)

1. Crie conta em [console.anthropic.com](https://console.anthropic.com/).
2. **Settings → API Keys** → crie uma chave.
3. **Settings → Billing** → adicione créditos (mínimo US$ 5).
4. Em `backend/.env`:

```env
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-api03-...
CLAUDE_MODEL=claude-haiku-4-5-20251001
```

### 3.3. Custos

Como o contexto é só metadados (algumas centenas de tokens), cada pergunta custa fração de centavo em qualquer um dos dois. O que controla o gasto quando há vários alunos é a cota mensal:

```env
FREE_AI_QUOTA=5
PRO_AI_QUOTA=200
```

---

## 4. Google Calendar (desligado nesta versão)

A sincronização está fora do ar na v1 pública. O escopo do Google Calendar é sensível, e usar fora do modo "Testing" (limitado a 100 usuários adicionados na mão) exige passar pela verificação do Google — processo que inclui vídeo demonstrativo e leva semanas.

O código continua em `backend/app/calendar_sync.py` e o endpoint `/api/sync-calendar` segue de pé. Com `VITE_GOOGLE_CLIENT_ID` vazio em `frontend/.env`, os botões simplesmente não aparecem na interface.

Para reativar em ambiente próprio, preencha o Client ID OAuth e recompile o frontend.

---

## 5. Publicando para outras pessoas

Detalhes no [README](../README.md#-publicando-num-domínio) e o plano completo por fases em [PLANO_PUBLICO.md](PLANO_PUBLICO.md).

O essencial:

1. Gere a chave de sessão e guarde como secret do provedor:

```bash
openssl rand -base64 32
```

2. Configure `SESSION_SECRET` e `APP_ENV=production`. Sem a primeira, o backend recusa subir em produção.

3. Monte um volume persistente e aponte `DATABASE_PATH` para dentro dele. Sem volume, cada deploy apaga a agenda de todos.

4. Rode `make test` antes de cada deploy — é o que garante que um aluno não vê os dados de outro.

---

## 6. Solução de problemas

### Venv criado no Windows não funciona no WSL

O `.venv` é específico do sistema. Apague e recrie:

```bash
rm -rf backend/.venv
./setup.sh
```

### `ModuleNotFoundError`

Falta ativar o `venv` ou instalar as dependências:

```bash
cd backend && source .venv/bin/activate && pip install -r requirements.txt
```

### Login falha

Use a matrícula com domínio (`294833@unoesc.edu.br`) e a mesma senha do Moodle. Confirme que consegue entrar em https://on.unoesc.edu.br pelo navegador.

### "Muitas tentativas de login"

O rate limit bloqueou após 5 erros seguidos. Espere 15 minutos, ou ajuste `LOGIN_MAX_ATTEMPTS` e `LOGIN_WINDOW_MINUTES` no `.env`.

### Sessões caem a cada restart

Em desenvolvimento isso é esperado: sem `SESSION_SECRET` definida, o backend gera uma chave efêmera e avisa no log. Defina uma chave fixa no `.env` para as sessões sobreviverem.

### Agenda vazia

Curso presencial normalmente não usa `assign`/`quiz` no Moodle, e sem isso o calendário não tem o que listar. O app atende bem quem faz EAD.

### Quero começar do zero

```bash
make clean
```

Ou, dentro do app, **Limpar cache** (mantém os concluídos) / **Excluir conta** (apaga tudo).
