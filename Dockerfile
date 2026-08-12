# Imagem única: o frontend é compilado e servido pelo próprio FastAPI.
# Um deploy, um domínio, sem CORS entre front e back — ver o mount de
# StaticFiles no fim de backend/app/main.py.

# --- estágio 1: build do frontend -------------------------------------------
FROM node:20-slim AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Sem VITE_GOOGLE_CLIENT_ID a sincronização com o Google Calendar não aparece
# na interface. É o estado da v1 pública: a tela de consentimento OAuth ainda
# não passou pela verificação do Google.
RUN npm run build

# --- estágio 2: runtime -----------------------------------------------------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    DATABASE_PATH=/data/agenda.db \
    FRONTEND_DIST=/app/static

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/tests ./tests
COPY --from=frontend /build/dist ./static

# O banco vive no volume montado em /data — sem ele, cada deploy zera a
# agenda de todo mundo.
VOLUME ["/data"]

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
