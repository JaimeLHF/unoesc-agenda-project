import React from 'react';
import type { AcademicEvent, EventType } from '../types';

interface EventListProps {
  events: AcademicEvent[];
  onSync: () => void;
  syncing: boolean;
}

/** Labels e cores dos tipos de evento */
const EVENT_TYPE_LABELS: Record<EventType, string> = {
  webconference: 'Webconferência',
  deadline: 'Entrega',
  exam: 'Prova',
  other: 'Outro',
};

const EVENT_TYPE_CLASSES: Record<EventType, string> = {
  webconference: 'badge--webconference',
  deadline: 'badge--deadline',
  exam: 'badge--exam',
  other: 'badge--other',
};

/**
 * Lista os eventos acadêmicos agrupados por data.
 * Exibe badge de tipo, status de sincronização e botão para sincronizar com o Google Calendar.
 */
const EventList: React.FC<EventListProps> = ({ events, onSync, syncing }) => {
  if (events.length === 0) {
    return (
      <div className="empty-state">
        Nenhum evento acadêmico identificado nas disciplinas selecionadas.
      </div>
    );
  }

  // Agrupa eventos por data (ISO 8601)
  const eventsByDate = events.reduce<Record<string, AcademicEvent[]>>((acc, event) => {
    const key = event.date || 'sem-data';
    if (!acc[key]) acc[key] = [];
    acc[key].push(event);
    return acc;
  }, {});

  // Ordena as datas cronologicamente
  const sortedDates = Object.keys(eventsByDate).sort();

  /** Formata a data ISO para exibição legível em pt-BR */
  const formatDate = (isoDate: string): string => {
    if (isoDate === 'sem-data') return 'Data não especificada';
    try {
      return new Date(isoDate + 'T00:00:00').toLocaleDateString('pt-BR', {
        weekday: 'long',
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      });
    } catch {
      return isoDate;
    }
  };

  return (
    <section className="event-list">
      <div className="event-list-header">
        <h3 className="section-title">
          Eventos encontrados ({events.length})
        </h3>
        <button
          className="btn-primary btn-sync"
          onClick={onSync}
          disabled={syncing || events.every((e) => e.synced)}
        >
          {syncing ? (
            <>
              <span className="spinner" aria-hidden="true" /> Sincronizando…
            </>
          ) : (
            '📅 Sincronizar com Google Calendar'
          )}
        </button>
      </div>

      {sortedDates.map((dateKey) => (
        <div key={dateKey} className="event-date-group">
          <h4 className="event-date-heading">{formatDate(dateKey)}</h4>

          <div className="event-cards">
            {eventsByDate[dateKey].map((event) => (
              <div key={event.id} className="event-card">
                <div className="event-card-top">
                  <span
                    className={`badge ${EVENT_TYPE_CLASSES[event.type as EventType] ?? 'badge--other'}`}
                  >
                    {EVENT_TYPE_LABELS[event.type as EventType] ?? event.type}
                  </span>
                  {event.synced && (
                    <span className="sync-status" title="Sincronizado com o Google Calendar">
                      ✅ Sincronizado
                    </span>
                  )}
                </div>

                <h5 className="event-title">{event.title}</h5>

                <div className="event-meta">
                  {event.time && (
                    <span className="event-time">🕐 {event.time}</span>
                  )}
                  <span className="event-subject">📚 {event.subject}</span>
                </div>

                {event.description && (
                  <p className="event-description">{event.description}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
};

export default EventList;
