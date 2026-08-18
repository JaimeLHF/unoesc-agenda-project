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
  /**
   * Início e fim do componente no Moodle, epoch em segundos. A matrícula
   * continua ativa depois do fim do semestre, então é `end_date` que diz se a
   * disciplina ainda está rolando ou já encerrou.
   */
  start_date?: number | null;
  end_date?: number | null;
  /** Nota final na escala 0–100 do Moodle; ausente enquanto nada foi lançado. */
  final_grade?: number | null;
}

/** Tipos possíveis de evento acadêmico */
export type EventType = 'webconference' | 'deadline' | 'exam' | 'other';

/** Representa um evento acadêmico vindo do calendário do Moodle */
export interface AcademicEvent {
  id: string;
  title: string;
  date: string;         // ISO 8601 (ex: "2025-06-10")
  time?: string;        // Horário no formato HH:MM, se disponível
  description: string;
  subject: string;
  type: EventType;
  synced?: boolean;     // Indica se já foi sincronizado com o Google Calendar
  url?: string;         // Link direto pra atividade no Moodle
  /**
   * Identidade do evento, calculada no backend a partir do id do Moodle.
   * Use sempre que existir: é imutável, ao contrário da chave derivada de
   * título + data, que mudava quando o professor renomeava a atividade.
   */
  stable_key?: string;
  event_type?: 'due' | 'open' | 'close';
  module?: string;      // assign | quiz | ...
  /**
   * De onde a data veio. `moodle_calendar` é o prazo cadastrado pelo
   * professor; `pdf_curso` foi lido do PDF da disciplina, e por isso a tela
   * marca — data interpretada por regex não vale o mesmo que data recebida.
   */
  source?: 'moodle_calendar' | 'moodle_course_text' | 'pdf_curso' | string;
}

/** Resposta do endpoint /api/scrape */
export interface ScrapeResponse {
  subjects: Subject[];
  calendar_events: AcademicEvent[];
}
