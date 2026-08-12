/**
 * Serviço de comunicação com a API FastAPI do backend UNOESC Agenda.
 * Todas as chamadas são feitas para http://localhost:8880 (redirecionadas
 * via proxy do Vite para evitar problemas de CORS durante o desenvolvimento).
 */

import axios from 'axios';
import type { LoginCredentials, Subject, AcademicEvent, ScrapeResponse } from '../types';

// Instância do Axios apontando para o backend FastAPI
const api = axios.create({
  baseURL: '/api', // O proxy do Vite redireciona /api → http://localhost:8880
  timeout: 300_000, // 5 min — scraping de quiz multi-página pode demorar
  headers: {
    'Content-Type': 'application/json',
  },
});

/* -------------------------------------------------------------------------
 * Sessão
 *
 * A senha vai para o backend uma única vez, em /api/login, e o que fica no
 * navegador é um token opaco. Ele mora só em memória — nada de localStorage,
 * que sobreviveria ao fechar a aba e ficaria exposto a XSS. O custo é que um
 * reload da página exige login de novo.
 *
 * Isso vale para o navegador. No servidor a senha é guardada cifrada, porque
 * o cliente do Moodle precisa relogar sozinho quando a sessão de lá expira —
 * o raciocínio inteiro está em `backend/app/crypto.py`, e a tela de login
 * avisa o aluno.
 * ----------------------------------------------------------------------- */

let authToken: string | null = null;

export function isAuthenticated(): boolean {
  return authToken !== null;
}

// Anexa o token em toda requisição que sair depois do login
api.interceptors.request.use((config) => {
  if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`;
  }
  return config;
});

// Detector simples de "backend offline": dispara CustomEvents no `window`
// que App.tsx escuta para mostrar/ocultar um banner. Um 401 significa sessão
// expirada — avisa a app para voltar à tela de login em vez de deixar o
// usuário preso numa tela que não responde mais.
api.interceptors.response.use(
  (response) => {
    window.dispatchEvent(new CustomEvent('backend-online'));
    return response;
  },
  (error) => {
    // Network error (sem resposta do servidor) → backend não respondeu
    if (!error.response) {
      window.dispatchEvent(new CustomEvent('backend-offline'));
    } else {
      window.dispatchEvent(new CustomEvent('backend-online'));
      if (error.response.status === 401) {
        authToken = null;
        window.dispatchEvent(new CustomEvent('session-expired'));
      }
    }
    return Promise.reject(error);
  },
);

/** Autentica no portal UNOESC e guarda o token da sessão. */
export async function login(credentials: LoginCredentials): Promise<void> {
  const { data } = await api.post<{ token: string }>('/login', credentials);
  authToken = data.token;
}

/** Encerra a sessão no backend e descarta o token local. */
export async function logout(): Promise<void> {
  try {
    if (authToken) await api.post('/logout');
  } finally {
    authToken = null;
  }
}

/**
 * Extrai as disciplinas com conteúdo + eventos já estruturados do calendário
 * Moodle. Exige sessão ativa.
 */
export async function scrapePortal(): Promise<ScrapeResponse> {
  const { data } = await api.post<{ subjects: Subject[]; calendar_events: AcademicEvent[] }>(
    '/scrape',
  );
  return { subjects: data.subjects, calendar_events: data.calendar_events ?? [] };
}

/**
 * Sincroniza os eventos acadêmicos com o Google Calendar do usuário.
 * @param events - Lista de eventos a sincronizar
 * @param googleToken - Access token OAuth2 do Google (obtido via GIS)
 */
export async function syncToCalendar(
  events: AcademicEvent[],
  googleToken: string,
): Promise<{ syncedEventIds: string[]; calendarLinks: string[] }> {
  const { data } = await api.post<{ synced_event_ids: string[]; calendar_links: string[] }>(
    '/sync-calendar',
    { events, google_token: googleToken },
  );
  return { syncedEventIds: data.synced_event_ids, calendarLinks: data.calendar_links };
}

/* -------------------------------------------------------------------------
 * Cache local (SQLite no backend)
 * ----------------------------------------------------------------------- */

export interface CacheResult {
  subjects: Subject[];
  events: AcademicEvent[];
  doneKeys: string[];
  lastScrapedAt: string | null;
}

/** Carrega disciplinas + eventos + concluídos do banco — sem fazer scraping. */
export async function fetchCache(): Promise<CacheResult> {
  const { data } = await api.get<{
    subjects: Subject[];
    events: AcademicEvent[];
    done_keys: string[];
    last_scraped_at: string | null;
  }>('/cache');
  return {
    subjects: data.subjects,
    events: data.events,
    doneKeys: data.done_keys,
    lastScrapedAt: data.last_scraped_at,
  };
}

/** Marca um evento como concluído. Retorna a lista atualizada de keys. */
export async function markEventDone(stableKey: string): Promise<string[]> {
  const { data } = await api.post<{ done_keys: string[] }>('/done-events', {
    stable_key: stableKey,
  });
  return data.done_keys;
}

/** Desmarca um evento concluído. Retorna a lista atualizada de keys. */
export async function unmarkEventDone(stableKey: string): Promise<string[]> {
  const { data } = await api.delete<{ done_keys: string[] }>('/done-events', {
    data: { stable_key: stableKey },
  });
  return data.done_keys;
}

/** Apaga o cache local (subjects, events, meta). Done events são preservados. */
export async function clearCache(): Promise<void> {
  await api.delete('/cache');
}

/* -------------------------------------------------------------------------
 * Conta
 * ----------------------------------------------------------------------- */

export interface Account {
  username: string;
  plan: string;
  assistantAvailable: boolean;
  assistantUsed: number;
  assistantLimit: number;
}

/** Dados da conta logada: plano e saldo do assistente. */
export async function fetchAccount(): Promise<Account> {
  const { data } = await api.get<{
    username: string;
    plan: string;
    assistant_available: boolean;
    assistant_used: number;
    assistant_limit: number;
  }>('/me');
  return {
    username: data.username,
    plan: data.plan,
    assistantAvailable: data.assistant_available,
    assistantUsed: data.assistant_used,
    assistantLimit: data.assistant_limit,
  };
}

/** Apaga a conta e todos os dados do aluno. Irreversível. */
export async function deleteAccount(): Promise<void> {
  await api.delete('/account');
  authToken = null;
}

/* -------------------------------------------------------------------------
 * Assistente de organização
 * ----------------------------------------------------------------------- */

export interface AssistantMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AssistantReply {
  response: string;
  used: number;
  limit: number;
}

/**
 * Pergunta ao assistente de organização (prioridades, plano de estudo).
 *
 * O contexto — quais atividades o aluno tem pendentes — é montado no backend
 * a partir do cache; o frontend só manda a conversa.
 */
export async function askAssistant(
  messages: AssistantMessage[],
): Promise<AssistantReply> {
  const { data } = await api.post<{ response: string; used: number; limit: number }>(
    '/assistant',
    { messages },
  );
  return data;
}

/**
 * Devolve o link direto da atividade (ou da disciplina) no Moodle.
 *
 * Antes isso era um link SSO gerado pelo portal, que abria já autenticado.
 * Agora é a URL real: o Moodle pede login na primeira vez e guarda o cookie
 * por 8 horas.
 */
export async function openCourse(
  subjectName: string,
  targetUrl?: string,
): Promise<string> {
  const { data } = await api.post<{ url: string }>('/open-course', {
    subject_name: subjectName,
    target_url: targetUrl,
  });
  return data.url;
}
