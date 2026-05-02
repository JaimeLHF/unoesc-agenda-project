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

// Detector simples de "backend offline": dispara CustomEvents no `window`
// que App.tsx escuta para mostrar/ocultar um banner.
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
    }
    return Promise.reject(error);
  },
);

/**
 * Faz login no portal UNOESC e retorna as disciplinas com conteúdo extraído
 * + eventos já estruturados do calendário Moodle.
 */
export async function scrapePortal(credentials: LoginCredentials): Promise<ScrapeResponse> {
  const { data } = await api.post<{ subjects: Subject[]; calendar_events: AcademicEvent[] }>(
    '/scrape',
    credentials,
  );
  return { subjects: data.subjects, calendar_events: data.calendar_events ?? [] };
}

/**
 * Envia disciplinas + eventos do calendário ao backend.
 * O backend mescla eventos do calendário Moodle (fonte estruturada) com
 * eventos extraídos do texto pelo Gemini (webconferências), deduplicando.
 */
export async function parseEvents(
  subjects: Subject[],
  calendarEvents: AcademicEvent[],
): Promise<AcademicEvent[]> {
  const { data } = await api.post<{ events: AcademicEvent[] }>('/parse-events', {
    subjects,
    calendar_events: calendarEvents,
  });
  return data.events;
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

/**
 * Extrai o conteúdo completo de uma atividade do Moodle (enunciado, critérios).
 */
export async function fetchActivityContent(
  username: string,
  password: string,
  subjectName: string,
  activityUrl: string,
): Promise<string> {
  const { data } = await api.post<{ content: string }>('/activity-content', {
    username,
    password,
    subject_name: subjectName,
    activity_url: activityUrl,
  });
  return data.content;
}

export interface AiMessage {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * Envia mensagens pro Gemini com contexto da atividade e retorna a resposta.
 */
export async function askAiHelp(
  activityContent: string,
  activityTitle: string,
  subjectName: string,
  messages: AiMessage[],
): Promise<string> {
  const { data } = await api.post<{ response: string }>('/ai-help', {
    activity_content: activityContent,
    activity_title: activityTitle,
    subject_name: subjectName,
    messages,
  });
  return data.response;
}

/**
 * Gera um link SSO fresco para abrir o Moodle da disciplina.
 * Retorna sso_url (cria sessão) e target_url (atividade específica).
 */
export async function openCourse(
  username: string,
  password: string,
  subjectName: string,
  targetUrl?: string,
): Promise<{ ssoUrl: string; targetUrl?: string }> {
  const { data } = await api.post<{ sso_url: string; target_url?: string }>('/open-course', {
    username,
    password,
    subject_name: subjectName,
    target_url: targetUrl,
  });
  return { ssoUrl: data.sso_url, targetUrl: data.target_url ?? undefined };
}
