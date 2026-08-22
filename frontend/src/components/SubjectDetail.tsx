import React, { useState } from 'react';
import type { Subject, AcademicEvent, EventType } from '../types';
import Icon from './Icon';
import GradesPanel from './GradesPanel';
import type { IconName } from './Icon';
import { useDoneEvents } from '../contexts/DoneEventsContext';
import { formatarPeso, mudancaDePrazo } from '../lib/avisos';

interface SubjectDetailProps {
  subject: Subject;
  events: AcademicEvent[];
  onBack: () => void;
  /**
   * Ausente enquanto o Google Calendar estiver desligado — o botão some junto.
   * A integração volta quando a tela de consentimento OAuth passar pela
   * verificação do Google.
   */
  onSync?: () => void;
  syncing: boolean;
  error?: string | null;
  /** Leva para a página da atividade — antes isso abria um modal. */
  onOpenEvent: (event: AcademicEvent) => void;
}

const SECTIONS: { type: EventType; label: string; icon: IconName }[] = [
  { type: 'webconference', label: 'Webconferências', icon: 'video' },
  { type: 'deadline', label: 'Entregas', icon: 'entrega' },
  { type: 'exam', label: 'Provas', icon: 'prova' },
  { type: 'other', label: 'Outros', icon: 'pin' },
];

/**
 * O Moodle devolve o link do item ora absoluto, ora relativo ("/mod/..."). O
 * relativo apontaria para o próprio app, que não tem essa rota.
 */
const MOODLE_BASE = 'https://on.unoesc.edu.br';

function moodleUrl(url: string): string {
  return url.startsWith('http') ? url : `${MOODLE_BASE}${url}`;
}

const BADGE_CLASS: Record<EventType, string> = {
  webconference: 'badge--webconference',
  deadline: 'badge--deadline',
  exam: 'badge--exam',
  other: 'badge--other',
};

function eventTimestamp(e: AcademicEvent): number {
  const d = new Date(`${e.date}T${e.time ?? '00:00'}:00`).getTime();
  return isNaN(d) ? Infinity : d;
}

function isPast(e: AcademicEvent): boolean {
  // Considera "passado" qualquer evento cujo dia já terminou
  const eventDay = new Date(`${e.date}T23:59:59`).getTime();
  return !isNaN(eventDay) && eventDay < Date.now();
}

const MONTH_ABBR_PT = [
  'JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN',
  'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ',
];

/** Decompõe uma data ISO em pedaços para o badge de data destacado. */
function dateBadge(iso: string): { day: string; month: string } {
  try {
    const d = new Date(`${iso}T00:00:00`);
    return {
      day: String(d.getDate()).padStart(2, '0'),
      month: MONTH_ABBR_PT[d.getMonth()] ?? '',
    };
  } catch {
    return { day: '?', month: '' };
  }
}

/** Etiqueta relativa: "Hoje", "Amanhã", "Em 3 dias", "Há 2 dias". */
function relativeLabel(iso: string, time?: string): string {
  try {
    const target = new Date(`${iso}T${time ?? '23:59'}:59`).getTime();
    const diffDays = Math.round((target - Date.now()) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return 'Hoje';
    if (diffDays === 1) return 'Amanhã';
    if (diffDays === -1) return 'Ontem';
    if (diffDays > 1) return `Em ${diffDays} dias`;
    return `Há ${Math.abs(diffDays)} dias`;
  } catch {
    return '';
  }
}

const SubjectDetail: React.FC<SubjectDetailProps> = ({
  subject,
  events,
  onBack,
  onSync,
  syncing,
  error,
  onOpenEvent,
}) => {
  const [hideDone, setHideDone] = useState(false);
  const { isDone, toggleDone } = useDoneEvents();

  const doneCount = events.filter((e) => isDone(e)).length;
  const visibleEvents = hideDone ? events.filter((e) => !isDone(e)) : events;

  // Agrupa por tipo + ordena por data crescente em cada grupo
  const byType: Record<EventType, AcademicEvent[]> = {
    webconference: [],
    deadline: [],
    exam: [],
    other: [],
  };
  for (const e of visibleEvents) {
    const type = (byType[e.type as EventType] ? (e.type as EventType) : 'other');
    byType[type].push(e);
  }
  for (const t of Object.keys(byType) as EventType[]) {
    byType[t].sort((a, b) => eventTimestamp(a) - eventTimestamp(b));
  }

  const allSynced = events.length > 0 && events.every((e) => e.synced);
  const upcomingCount = events.filter((e) => !isPast(e)).length;
  const novidades = subject.new_materials ?? [];
  const semData = subject.pending_activities ?? [];

  return (
    <section className="subject-detail">
      <div className="subject-detail__top">
        <button type="button" className="btn-back" onClick={onBack}>
          <Icon name="voltar" />
          Voltar
        </button>
        {onSync && (
          <button
            type="button"
            className="btn-primary btn-sync"
            onClick={onSync}
            disabled={syncing || allSynced || events.length === 0}
          >
            {syncing ? (
              <>
                <span className="spinner" aria-hidden="true" /> Sincronizando…
              </>
            ) : allSynced ? (
              <>
                <Icon name="check" /> Tudo sincronizado
              </>
            ) : (
              <>
                <Icon name="calendario" /> Sincronizar com o Google Calendar
              </>
            )}
          </button>
        )}
      </div>

      <div className="subject-detail__header">
        <div>
          {/* Mesma separação da grade: código como etiqueta, nome em destaque. */}
          {(() => {
            const match = subject.name.match(/^(\d{3,})\s*-\s*(.+)$/);
            return match ? (
              <>
                <span className="subject-detail__code">{match[1]}</span>
                <h2 className="subject-detail__title">{match[2]}</h2>
              </>
            ) : (
              <h2 className="subject-detail__title">{subject.name}</h2>
            );
          })()}
          <p className="subject-detail__meta">
            {events.length} {events.length === 1 ? 'evento' : 'eventos'}
            {upcomingCount > 0 && ` · ${upcomingCount} ${upcomingCount === 1 ? 'futuro' : 'futuros'}`}
            {doneCount > 0 && ` · ${doneCount} concluído${doneCount === 1 ? '' : 's'}`}
          </p>
        </div>
        {doneCount > 0 && (
          <label className="filter-toggle">
            <input
              type="checkbox"
              checked={hideDone}
              onChange={(e) => setHideDone(e.target.checked)}
            />
            <span>Ocultar concluídos</span>
          </label>
        )}
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <Icon name="alerta" />
          {error}
        </div>
      )}

      {/* O boletim vem antes da lista de eventos: quem abre uma disciplina no
          fim do semestre está atrás da nota, não do calendário. */}
      <GradesPanel subjectName={subject.name} />

      {/*
        O que o professor publicou desde a última visita. Fica acima dos
        eventos porque em curso presencial não existe evento nenhum — este é o
        único conteúdo que a sala produz, e era o motivo de o aluno abrir o
        Moodle disciplina por disciplina.
      */}
      {novidades.length > 0 && (
        <section className="novidades">
          <h3 className="novidades__titulo">
            <Icon name="pin" size={0.95} />
            Publicado recentemente na sala
          </h3>
          <ul className="novidades__lista">
            {novidades.map((item, i) => (
              <li key={`${item.name}-${i}`} className="novidades__item">
                {item.url ? (
                  <a
                    className="novidades__link"
                    href={moodleUrl(item.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {item.name}
                  </a>
                ) : (
                  <span>{item.name}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {events.length === 0 && semData.length === 0 ? (
        <div className="empty-state">Nenhum evento identificado nesta disciplina.</div>
      ) : (
        <div className="subject-detail__sections">
          {SECTIONS.map(({ type, label, icon }) => {
            const list = byType[type];
            if (list.length === 0) return null;

            return (
              <div key={type} className="event-section">
                <h3 className="event-section__title">
                  <span className={`event-section__icon event-section__icon--${type}`}>
                    <Icon name={icon} />
                  </span>
                  {label}
                  <span className="event-section__count">{list.length}</span>
                </h3>

                <div className="event-cards">
                  {list.map((event) => {
                    const past = isPast(event);
                    const done = isDone(event);
                    const { day, month } = dateBadge(event.date);
                    const rel = relativeLabel(event.date, event.time);
                    const mudanca = mudancaDePrazo(event);
                    const peso = formatarPeso(event.weight);
                    const cardClass = [
                      'event-card',
                      'event-card--clickable',
                      past ? 'event-card--past' : '',
                      done ? 'event-card--done' : '',
                    ]
                      .filter(Boolean)
                      .join(' ');
                    return (
                      <div key={event.id} className={cardClass}>
                        <label
                          className="event-done-toggle"
                          title={done ? 'Marcar como pendente' : 'Marcar como concluído'}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={done}
                            onChange={() => toggleDone(event)}
                          />
                          <span className="event-done-toggle__check" aria-hidden="true">
                            <Icon name="check" size={0.85} />
                          </span>
                        </label>

                        <button
                          type="button"
                          className="event-card-clickarea"
                          onClick={() => onOpenEvent(event)}
                        >
                          <div className="event-date-badge">
                            <span className="event-date-badge__day">{day}</span>
                            <span className="event-date-badge__month">{month}</span>
                            {event.time && (
                              <span className="event-date-badge__time">{event.time}</span>
                            )}
                          </div>

                          <div className="event-card-body">
                            <div className="event-card-top">
                              <span className={`badge ${BADGE_CLASS[type]}`}>
                                {label.replace(/s$/, '')}
                              </span>
                              {done && (
                                <span className="status-pill status-pill--done">
                                  <Icon name="check" size={0.9} /> Concluído
                                </span>
                              )}
                              {rel && !past && !done && (
                                <span className="event-card-relative">{rel}</span>
                              )}
                              {past && !done && (
                                <span className="status-pill status-pill--past">Encerrado</span>
                              )}
                              {event.synced && (
                                <span className="status-pill status-pill--synced" title="Sincronizado">
                                  <Icon name="calendario" size={0.9} />
                                </span>
                              )}
                              {/*
                                A data mudou depois que o aluno já tinha visto
                                a antiga. Sem este selo, quem se programou para
                                a data velha não teria como perceber a troca.
                              */}
                              {mudanca && (
                                <span className="status-pill status-pill--mudou">
                                  {mudanca.rotulo} · era {mudanca.de}
                                </span>
                              )}
                              {peso && (
                                <span
                                  className="status-pill status-pill--peso"
                                  title="Peso informado no PDF da disciplina"
                                >
                                  {peso}
                                </span>
                              )}
                              {event.source === 'atividade_moodle' && (
                                <span
                                  className="status-pill status-pill--origem"
                                  title="Prazo lido na página da atividade: o professor não cadastrou esta data no calendário do Moodle."
                                >
                                  Da sala
                                </span>
                              )}
                            </div>

                            <h4 className="event-title">{event.title}</h4>

                            {event.description && (
                              <p className="event-description">{event.description}</p>
                            )}
                          </div>
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/*
            Avaliação que a sala tem e que não tem data em canto nenhum — nem
            no calendário, nem na própria página. Fica aqui embaixo, junto dos
            eventos e não no card de novidades, porque "prova sem data
            marcada" é informação de agenda: o aluno precisa saber que ela
            existe para perguntar ao professor quando é.
          */}
          {semData.length > 0 && (
            <div className="event-section">
              <h3 className="event-section__title">
                <span className="event-section__icon event-section__icon--other">
                  <Icon name="alerta" />
                </span>
                Sem data marcada
                <span className="event-section__count">{semData.length}</span>
              </h3>

              <ul className="sem-data">
                {semData.map((item, i) => (
                  <li key={`${item.name}-${i}`} className="sem-data__item">
                    {item.url ? (
                      <a
                        className="sem-data__link"
                        href={moodleUrl(item.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {item.name}
                      </a>
                    ) : (
                      <span>{item.name}</span>
                    )}
                  </li>
                ))}
              </ul>
              <p className="sem-data__nota">
                Estas atividades estão na sala, mas o Moodle não informa prazo
                para elas. Confirme a data com o professor.
              </p>
            </div>
          )}
        </div>
      )}

    </section>
  );
};

export default SubjectDetail;
