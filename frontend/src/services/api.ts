/**
 * Serviço de comunicação com a API FastAPI do backend UNOESC Agenda.
 * Todas as chamadas são feitas para http://localhost:8000 (redirecionadas
 * via proxy do Vite para evitar problemas de CORS durante o desenvolvimento).
 */

import axios from 'axios';
import type { LoginCredentials, Subject, AcademicEvent, ScrapeResponse } from '../types';

// Instância do Axios apontando para o backend FastAPI
const api = axios.create({
  baseURL: '/api', // O proxy do Vite redireciona /api → http://localhost:8000
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Faz login no portal UNOESC e retorna as disciplinas com conteúdo extraído.
 * @param credentials - Usuário e senha do portal
 */
export async function scrapePortal(credentials: LoginCredentials): Promise<ScrapeResponse> {
  const { data } = await api.post<{ subjects: Subject[] }>('/scrape', credentials);
  // O endpoint /scrape retorna apenas subjects; events são obtidos via parseEvents
  return { subjects: data.subjects, events: [] };
}

/**
 * Envia as disciplinas ao backend para que o Gemini extraia os eventos acadêmicos.
 * @param subjects - Lista de disciplinas com conteúdo de texto
 */
export async function parseEvents(subjects: Subject[]): Promise<AcademicEvent[]> {
  const { data } = await api.post<{ events: AcademicEvent[] }>('/parse-events', { subjects });
  return data.events;
}

/**
 * Sincroniza os eventos acadêmicos com o Google Calendar do usuário.
 * @param events - Lista de eventos a sincronizar
 */
export async function syncToCalendar(events: AcademicEvent[]): Promise<void> {
  // O token OAuth do Google é obtido pelo frontend via Google Identity Services
  const googleToken = (window as { googleOAuthToken?: string }).googleOAuthToken ?? '';
  await api.post('/sync-calendar', { events, google_token: googleToken });
}
