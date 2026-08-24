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
 * navegador é um token opaco.
 *
 * Ele vive no `localStorage`, sempre. Já foi `sessionStorage`, que morre com a
 * aba — e no iPhone fechar o app instalado é fechar a aba, então o aluno
 * reabria o ícone e caía no login todo dia. Depois virou escolha, numa caixa
 * "Manter conectado" que ninguém desmarcava; a caixa saiu e ficou o que ela
 * já entregava marcada. Quem entra num computador compartilhado sai pelo
 * perfil, que é o botão que sempre resolveu isso.
 *
 * Contra XSS os dois valem o mesmo — um script injetado na página usa o token
 * em memória do mesmo jeito. A proteção real seria cookie httpOnly, que exige
 * CSRF e um proxy no dev; está anotado como evolução.
 *
 * Isso vale para o navegador. No servidor a senha é guardada cifrada, porque
 * o cliente do Moodle precisa relogar sozinho quando a sessão de lá expira —
 * o raciocínio inteiro está em `backend/app/crypto.py`, e a tela de login
 * avisa o aluno.
 * ----------------------------------------------------------------------- */

const TOKEN_KEY = 'agenda_token';

/* Navegador em modo restrito (Safari privado antigo, iframe sem permissão)
   pode barrar o storage. Aí a sessão volta a viver só em memória, como antes. */
function lerToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

let authToken: string | null = lerToken();

/**
 * Guarda o token no `localStorage`. Limpa o `sessionStorage` junto: quem
 * entrou antes com a caixa desmarcada tem uma cópia velha do token lá, e
 * deixá-la para trás faria `lerToken()` achar duas.
 */
function guardarToken(token: string | null): void {
  authToken = token;
  try {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    }
  } catch {
    /* sem storage: o token continua valendo nesta aba, só não sobrevive ao reload */
  }
}

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
        guardarToken(null);
        window.dispatchEvent(new CustomEvent('session-expired'));
      }
    }
    return Promise.reject(error);
  },
);

/**
 * Autentica no portal UNOESC e guarda o token da sessão.
 */
export async function login(credentials: LoginCredentials): Promise<void> {
  const { data } = await api.post<{ token: string }>('/login', credentials);
  guardarToken(data.token);
}

/** Encerra a sessão no backend e descarta o token local. */
export async function logout(): Promise<void> {
  try {
    if (authToken) await api.post('/logout');
  } finally {
    guardarToken(null);
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
  /** Dono do serviço. Só o backend sabe — a lista é secret de servidor. */
  isAdmin: boolean;
}

/** Dados da conta logada: plano e saldo do assistente. */
export async function fetchAccount(): Promise<Account> {
  const { data } = await api.get<{
    username: string;
    plan: string;
    assistant_available: boolean;
    assistant_used: number;
    assistant_limit: number;
    is_admin?: boolean;
  }>('/me');
  return {
    username: data.username,
    plan: data.plan,
    assistantAvailable: data.assistant_available,
    assistantUsed: data.assistant_used,
    assistantLimit: data.assistant_limit,
    isAdmin: data.is_admin === true,
  };
}

/* -------------------------------------------------------------------------
 * Painel do dono
 * ----------------------------------------------------------------------- */

export interface AdminConta {
  username: string;
  /** Nome no Moodle. Vazio até o aluno abrir o app pela primeira vez. */
  nome: string;
  criado_em: string;
  ultimo_acesso: string;
  plano: string;
  disciplinas: number;
  eventos: number;
  concluidos: number;
  aparelhos: number;
  sessoes: number;
  assinou_ics: boolean;
  lumi: number;
}

export interface AdminServidor {
  desde: string;
  uptime_s: number;
  requisicoes: number;
  amostras: number;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  por_rota: [string, number][];
  por_status: [number, number][];
  lentas: { rota: string; ms: number; quando: string }[];
  falhas: { codigo: string; contexto: string; erro: string; quando: string }[];
}

export interface AdminPanorama {
  contas: AdminConta[];
  resumo: Record<string, number>;
  por_dia: { dia: string; contas: number }[];
  servidor: AdminServidor;
}

/**
 * Estado do serviço, lido ao vivo. Responde 404 para quem não é dono — o
 * frontend nunca deve tratar isso como erro a mostrar na tela do aluno.
 */
export async function fetchPanorama(): Promise<AdminPanorama> {
  const { data } = await api.get<AdminPanorama>('/admin/panorama');
  return data;
}

/** O cadastro do aluno como o Moodle o guarda. */
export interface MoodleProfile {
  moodle_id: number | null;
  fullname: string;
  firstname: string;
  lastname: string;
  /** Só a matrícula ("294833"); o endereço completo está em `email`. */
  username: string;
  email: string;
  department: string;
  institution: string;
  city: string;
  country: string;
  timezone: string;
  first_access: string | null;
  last_access: string | null;
  /** Foto já embutida como `data:` — a URL do Moodle exige a sessão de lá. */
  avatar: string | null;
}

export interface ProfileStats {
  subjects: number;
  events_total: number;
  events_upcoming: number;
  events_done: number;
  next_event_title: string | null;
  next_event_date: string | null;
  next_event_time: string | null;
  next_event_subject: string | null;
  last_scraped_at: string | null;
}

export interface Profile {
  account_username: string;
  plan: string;
  member_since: string | null;
  last_login_at: string | null;
  /** Nulo quando o Moodle não respondeu; `moodle_error` diz o motivo. */
  moodle: MoodleProfile | null;
  moodle_error: string | null;
  stats: ProfileStats;
}

/** Perfil completo: cadastro no Moodle + conta no app + resumo da agenda. */
export async function fetchProfile(): Promise<Profile> {
  const { data } = await api.get<Profile>('/profile');
  return data;
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

/** Um anexo da atividade — quase sempre o PDF com o enunciado. */
export interface ActivityFile {
  /** Texto do link, ou o nome do arquivo quando o link só diz "Clique aqui". */
  name: string;
  url: string;
  filename?: string | null;
  /** Extensão em maiúscula ("PDF"), quando dá para saber pela URL. */
  ext?: string | null;
}

export interface ActivityDetail {
  stable_key: string;
  title: string;
  date: string;
  time?: string | null;
  description: string;
  subject: string;
  type: string;
  url: string;
  done: boolean;
  synced: boolean;
  /** Página da atividade lida no Moodle com a sessão do servidor. */
  content: {
    /** O enunciado, já sem a tabela de status e sem rótulo de botão. */
    intro: string;
    /** Status do envio como pares rótulo/valor, do jeito que o Moodle mostra. */
    status: { label: string; value: string }[];
    files: ActivityFile[];
    url: string;
  } | null;
  /** Por que o conteúdo não veio. A página abre mesmo assim. */
  content_error: string | null;
}

/* -------------------------------------------------------------------------
 * Envio de tarefa
 *
 * O app salva o envio como **rascunho** no Moodle: o arquivo passa a aparecer
 * na tarefa e pode ser trocado ou apagado depois. O "enviar para avaliação",
 * que quase nunca dá para desfazer, continua sendo um clique do aluno lá.
 * ----------------------------------------------------------------------- */

export interface StatusLinha {
  label: string;
  value: string;
}

export interface ArquivoNoRascunho {
  name: string;
  size: number;
}

export interface SubmissionInfo {
  can_submit: boolean;
  /** Por que não dá para enviar agora — prazo fechado, envio travado. */
  reason: string | null;
  accepts_files: boolean;
  accepts_text: boolean;
  max_files: number;
  max_file_mb: number;
  /** Já anexado na tarefa — vai junto quando salvar. */
  existing_files: ArquivoNoRascunho[];
  /** Entregue para avaliação: a tela mostra o aviso, não o formulário. */
  submitted: boolean;
  /** Rascunho salvo: ainda dá para mexer. */
  draft: boolean;
  submitted_label: string | null;
  submitted_at: string | null;
  status: StatusLinha[];
}

export interface SubmissionResult {
  saved: boolean;
  /** A tabela de status relida no Moodle depois de salvar. */
  status: StatusLinha[];
  moodle_url: string;
}

/** O que esta tarefa aceita e como está o envio agora. */
export async function fetchSubmissionInfo(stableKey: string): Promise<SubmissionInfo> {
  const { data } = await api.get<SubmissionInfo>(
    `/submission/${encodeURIComponent(stableKey)}`,
  );
  return data;
}

/** Salva arquivos e/ou texto na tarefa, como rascunho. */
export async function submitAssignment(
  stableKey: string,
  files: File[],
  onlineText: string,
): Promise<SubmissionResult> {
  const form = new FormData();
  files.forEach((f) => form.append('files', f, f.name));
  form.append('online_text', onlineText);

  const { data } = await api.post<SubmissionResult>(
    `/submission/${encodeURIComponent(stableKey)}`,
    form,
    // O axios monta o boundary sozinho quando o header sai do caminho.
    { headers: { 'Content-Type': undefined } },
  );
  return data;
}

export async function fetchActivity(stableKey: string): Promise<ActivityDetail> {
  const { data } = await api.get<ActivityDetail>(
    `/activity/${encodeURIComponent(stableKey)}`,
  );
  return data;
}

/* -------------------------------------------------------------------------
 * Calendário assinável
 *
 * Um endereço `.ics` que o Google Agenda, o Apple Calendário ou o Outlook
 * buscam sozinhos de tempos em tempos. A chave da URL é a credencial — quem
 * tiver o endereço vê a agenda —, por isso existe o botão de trocar.
 * ----------------------------------------------------------------------- */

export async function fetchCalendarFeed(): Promise<string> {
  const { data } = await api.get<{ url: string }>('/calendar-feed');
  return data.url;
}

export async function resetCalendarFeed(): Promise<string> {
  const { data } = await api.post<{ url: string }>('/calendar-feed/reset');
  return data.url;
}

/* -------------------------------------------------------------------------
 * Boletim da disciplina
 * ----------------------------------------------------------------------- */

export interface GradeItem {
  name: string;
  weight: number | null;
  grade: number | null;
  max: number | null;
}

export interface Grades {
  items: GradeItem[];
  /** Média parcial na escala 0–10. */
  current: number | null;
  pending_count: number;
  pending_weight: number;
  /** Nota necessária no que falta; nulo quando o cálculo não é confiável. */
  needed: number | null;
  passing_grade: number;
}

export async function fetchGrades(subjectName: string): Promise<Grades> {
  const { data } = await api.post<Grades>('/grades', { subject_name: subjectName });
  return data;
}

/* -------------------------------------------------------------------------
 * Notificação push
 *
 * O aviso na tela bloqueada. No iPhone só existe com o app instalado na tela
 * inicial — ver `InstalarNoCelular`.
 * ----------------------------------------------------------------------- */

export interface PushConfig {
  /** O servidor tem chave VAPID? Sem isso o recurso não aparece. */
  enabled: boolean;
  public_key: string | null;
  /** Aparelhos já inscritos nesta conta. */
  devices: number;
}

export async function fetchPushConfig(): Promise<PushConfig> {
  const { data } = await api.get<PushConfig>('/push/config');
  return data;
}

export async function subscribePush(inscricao: PushSubscriptionJSON): Promise<PushConfig> {
  const { data } = await api.post<PushConfig>('/push/subscribe', inscricao);
  return data;
}

export async function unsubscribePush(endpoint?: string): Promise<PushConfig> {
  const { data } = await api.delete<PushConfig>('/push/subscribe', {
    data: { endpoint: endpoint ?? null },
  });
  return data;
}

export async function testPush(): Promise<void> {
  await api.post('/push/test');
}
