// Interfaces TypeScript compartilhadas entre componentes e serviços

/** Credenciais de login do portal UNOESC */
export interface LoginCredentials {
  username: string;
  password: string;
}

/** Item publicado na sala da disciplina depois que o aluno já usava o app. */
export interface NewMaterial {
  name: string;
  url?: string | null;
  modname?: string | null;
  /** ISO 8601, UTC — quando o app viu esse item pela primeira vez. */
  first_seen_at?: string | null;
}

/** Representa uma disciplina com seu conteúdo extraído */
export interface Subject {
  id: string;
  name: string;
  content?: string;
  /**
   * O que o professor publicou nos últimos dias. Em curso presencial é o único
   * sinal que a sala emite — lá não existe evento de calendário nenhum.
   */
  new_materials?: NewMaterial[];
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
  /**
   * A data que este evento tinha antes de o professor mexer. Só vem enquanto a
   * mudança é recente; é o que permite a tela dizer "adiado" em vez de trocar
   * o dia em silêncio. Ver `lib/avisos.ts`.
   */
  previous_date?: string | null;
  /** Peso da avaliação, quando o PDF da disciplina informa. */
  weight?: number | null;
}

/** Resposta do endpoint /api/scrape */
export interface ScrapeResponse {
  subjects: Subject[];
  calendar_events: AcademicEvent[];
}
