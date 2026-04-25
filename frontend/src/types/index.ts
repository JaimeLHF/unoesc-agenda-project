// Interfaces TypeScript compartilhadas entre componentes e serviços

/** Credenciais de login do portal UNOESC */
export interface LoginCredentials {
  username: string;
  password: string;
}

/** Representa uma disciplina com seu conteúdo extraído */
export interface Subject {
  id: string;
  name: string;
  content?: string;
}

/** Tipos possíveis de evento acadêmico */
export type EventType = 'webconference' | 'deadline' | 'exam' | 'other';

/** Representa um evento acadêmico identificado pelo Gemini */
export interface AcademicEvent {
  id: string;
  title: string;
  date: string;         // ISO 8601 (ex: "2025-06-10")
  time?: string;        // Horário no formato HH:MM, se disponível
  description: string;
  subject: string;
  type: EventType;
  synced?: boolean;     // Indica se já foi sincronizado com o Google Calendar
  url?: string;         // Link direto pro evento no portal (Moodle)
}

/** Resposta do endpoint /api/scrape */
export interface ScrapeResponse {
  subjects: Subject[];
  calendar_events: AcademicEvent[];
}
