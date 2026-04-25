import React from 'react';
import type { Subject, AcademicEvent, EventType } from '../types';
import EventAlerts from './EventAlerts';
import { useDoneEvents } from '../contexts/DoneEventsContext';

interface SubjectListProps {
  subjects: Subject[];
  events: AcademicEvent[];
  onSelectSubject: (id: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
  refreshError?: string | null;
  onLogout: () => void;
  onClearCache: () => void;
  lastScrapedAt?: string | null;
}

/** Formata "X minutos atrás" / "ontem" a partir de um timestamp ISO. */
function formatRelative(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    const ts = new Date(iso).getTime();
    if (isNaN(ts)) return null;
    const diffMin = Math.round((Date.now() - ts) / 60000);
    if (diffMin < 1) return 'agora há pouco';
    if (diffMin < 60) return `${diffMin} min atrás`;
    const diffHours = Math.round(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h atrás`;
    const diffDays = Math.round(diffHours / 24);
    if (diffDays === 1) return 'ontem';
    return `${diffDays} dias atrás`;
  } catch {
    return null;
  }
}

const TYPE_LABELS: Record<EventType, { singular: string; plural: string }> = {
  webconference: { singular: 'webconferência', plural: 'webconferências' },
  deadline: { singular: 'entrega', plural: 'entregas' },
  exam: { singular: 'prova', plural: 'provas' },
  other: { singular: 'evento', plural: 'eventos' },
};

const TYPE_ORDER: EventType[] = ['webconference', 'deadline', 'exam', 'other'];

/** Calcula stats de uma disciplina baseado em seus eventos. */
function computeStats(events: AcademicEvent[]) {
  const now = new Date();
  now.setHours(0, 0, 0, 0);

  const counts: Record<EventType, number> = {
    webconference: 0,
    deadline: 0,
    exam: 0,
    other: 0,
  };
  let upcomingCount = 0;
  let nextEvent: AcademicEvent | null = null;
  let nextEventDate = Infinity;

  for (const e of events) {
    counts[e.type as EventType] = (counts[e.type as EventType] ?? 0) + 1;
    const d = new Date(`${e.date}T${e.time ?? '00:00'}:00`).getTime();
    if (!isNaN(d) && d >= now.getTime()) {
      upcomingCount += 1;
      if (d < nextEventDate) {
        nextEventDate = d;
        nextEvent = e;
      }
    }
  }

  return { counts, upcomingCount, nextEvent };
}

function formatNextEventDate(iso: string, time?: string): string {
  try {
    const d = new Date(`${iso}T${time ?? '00:00'}:00`);
    const dateStr = d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
    return time ? `${dateStr} às ${time}` : dateStr;
  } catch {
    return iso;
  }
}

const SubjectList: React.FC<SubjectListProps> = ({
  subjects,
  events,
  onSelectSubject,
  onRefresh,
  refreshing,
  refreshError,
  onLogout,
  onClearCache,
  lastScrapedAt,
}) => {
  const { isDone } = useDoneEvents();
  const lastScrapedRel = formatRelative(lastScrapedAt);
  return (
    <section className="subject-grid-section">
      <div className="subject-grid-header">
        <div>
          <h2 className="section-title">Suas disciplinas</h2>
          <p className="section-subtitle">
            Clique em uma disciplina para ver seus eventos e sincronizá-los.
            {lastScrapedRel && (
              <span className="last-scraped"> · Atualizado {lastScrapedRel}</span>
            )}
          </p>
        </div>
        <div className="subject-grid-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={onRefresh}
            disabled={refreshing}
            title="Buscar disciplinas e eventos novamente no portal"
          >
            {refreshing ? (
              <>
                <span className="spinner spinner--dark" aria-hidden="true" /> Atualizando…
              </>
            ) : (
              '🔄 Atualizar'
            )}
          </button>
          <button
            type="button"
            className="btn-link"
            onClick={onClearCache}
            title="Apaga subjects e eventos do banco local"
          >
            Limpar cache
          </button>
          <button type="button" className="btn-link" onClick={onLogout}>
            Sair
          </button>
        </div>
      </div>

      {refreshError && (
        <div className="error-banner" role="alert">
          ⚠️ {refreshError}
        </div>
      )}

      <EventAlerts events={events} />

      {subjects.length === 0 ? (
        <div className="empty-state">Nenhuma disciplina encontrada no portal.</div>
      ) : (
        <div className="subject-grid-large">
        {subjects.map((subject) => {
          const subjEvents = events.filter((e) => e.subject === subject.name);
          // Próximo evento ignora os já concluídos — esses não precisam mais aparecer em destaque
          const pendingEvents = subjEvents.filter((e) => !isDone(e));
          const { counts, upcomingCount, nextEvent } = computeStats(pendingEvents);
          const total = subjEvents.length;
          const doneInSubject = subjEvents.filter((e) => isDone(e)).length;

          const breakdown = TYPE_ORDER
            .filter((t) => counts[t] > 0)
            .map((t) => `${counts[t]} ${counts[t] === 1 ? TYPE_LABELS[t].singular : TYPE_LABELS[t].plural}`)
            .join(' · ');

          return (
            <button
              key={subject.id}
              type="button"
              className="subject-card-large"
              onClick={() => onSelectSubject(subject.id)}
              disabled={total === 0}
            >
              <div className="subject-card-large__header">
                <span className="subject-card-large__name">{subject.name}</span>
                <span className="subject-card-large__total">
                  {total} {total === 1 ? 'evento' : 'eventos'}
                </span>
              </div>

              {total > 0 ? (
                <>
                  <div className="subject-card-large__breakdown">{breakdown}</div>
                  {doneInSubject > 0 && (
                    <div className="subject-card-large__done">
                      ✓ {doneInSubject} de {total} concluído{doneInSubject === 1 ? '' : 's'}
                    </div>
                  )}
                  {nextEvent ? (
                    <div className="subject-card-large__next">
                      <span className="subject-card-large__next-label">Próximo:</span>
                      <span className="subject-card-large__next-title">{nextEvent.title}</span>
                      <span className="subject-card-large__next-date">
                        {formatNextEventDate(nextEvent.date, nextEvent.time)}
                      </span>
                    </div>
                  ) : (
                    <div className="subject-card-large__next subject-card-large__next--past">
                      Sem eventos futuros — {upcomingCount === 0 ? 'todos encerrados' : ''}
                    </div>
                  )}
                </>
              ) : (
                <div className="subject-card-large__empty">Nenhum evento identificado</div>
              )}
            </button>
          );
        })}
        </div>
      )}
    </section>
  );
};

export default SubjectList;
