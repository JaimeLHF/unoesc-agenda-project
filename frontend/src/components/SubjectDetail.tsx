import React, { useState } from 'react';
import type { Subject, AcademicEvent, EventType } from '../types';
import EventModal from './EventModal';
import { useDoneEvents } from '../contexts/DoneEventsContext';

interface SubjectDetailProps {
  subject: Subject;
  events: AcademicEvent[];
  onBack: () => void;
  onSync: () => void;
  syncing: boolean;
  error?: string | null;
}

const SECTIONS: { type: EventType; label: string; emoji: string }[] = [
  { type: 'webconference', label: 'Webconferências', emoji: '🎥' },
  { type: 'deadline', label: 'Entregas', emoji: '📤' },
  { type: 'exam', label: 'Provas', emoji: '📝' },
  { type: 'other', label: 'Outros', emoji: '📌' },
];

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
}) => {
  const [openEvent, setOpenEvent] = useState<AcademicEvent | null>(null);
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

  return (
    <section className="subject-detail">
      <div className="subject-detail__top">
        <button type="button" className="btn-link" onClick={onBack}>
          ← Voltar
        </button>
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
            '✅ Tudo sincronizado'
          ) : (
            '📅 Sincronizar todos com Google Calendar'
          )}
        </button>
      </div>

      <div className="subject-detail__header">
        <div>
          <h2 className="subject-detail__title">{subject.name}</h2>
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
          ⚠️ {error}
        </div>
      )}

      {events.length === 0 ? (
        <div className="empty-state">Nenhum evento identificado nesta disciplina.</div>
      ) : (
        <div className="subject-detail__sections">
          {SECTIONS.map(({ type, label, emoji }) => {
            const list = byType[type];
            if (list.length === 0) return null;

            return (
              <div key={type} className="event-section">
                <h3 className="event-section__title">
                  <span className="event-section__emoji">{emoji}</span>
                  {label}
                  <span className="event-section__count">({list.length})</span>
                </h3>

                <div className="event-cards">
                  {list.map((event) => {
                    const past = isPast(event);
                    const done = isDone(event);
                    const { day, month } = dateBadge(event.date);
                    const rel = relativeLabel(event.date, event.time);
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
                          <span className="event-done-toggle__check" aria-hidden="true">✓</span>
                        </label>

                        <button
                          type="button"
                          className="event-card-clickarea"
                          onClick={() => setOpenEvent(event)}
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
                                <span className="status-pill status-pill--done">✓ Concluído</span>
                              )}
                              {rel && !past && !done && (
                                <span className="event-card-relative">{rel}</span>
                              )}
                              {past && !done && (
                                <span className="status-pill status-pill--past">Encerrado</span>
                              )}
                              {event.synced && (
                                <span className="status-pill status-pill--synced" title="Sincronizado">
                                  📅
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
        </div>
      )}

      <EventModal event={openEvent} onClose={() => setOpenEvent(null)} />
    </section>
  );
};

export default SubjectDetail;
