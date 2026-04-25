import React, { useEffect } from 'react';
import type { AcademicEvent, EventType } from '../types';
import { useDoneEvents } from '../contexts/DoneEventsContext';

interface EventModalProps {
  event: AcademicEvent | null;
  onClose: () => void;
}

const TYPE_LABELS: Record<EventType, string> = {
  webconference: 'Webconferência',
  deadline: 'Entrega',
  exam: 'Prova',
  other: 'Evento',
};

const TYPE_BADGES: Record<EventType, string> = {
  webconference: 'badge--webconference',
  deadline: 'badge--deadline',
  exam: 'badge--exam',
  other: 'badge--other',
};

function formatFullDate(iso: string, time?: string): string {
  try {
    const d = new Date(`${iso}T${time ?? '00:00'}:00`);
    const dateStr = d.toLocaleDateString('pt-BR', {
      weekday: 'long',
      day: '2-digit',
      month: 'long',
      year: 'numeric',
    });
    return time ? `${dateStr} às ${time}` : dateStr;
  } catch {
    return iso;
  }
}

function relativeDays(iso: string, time?: string): string {
  try {
    const target = new Date(`${iso}T${time ?? '23:59'}:59`).getTime();
    const now = Date.now();
    const diffMs = target - now;
    const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return 'Hoje';
    if (diffDays === 1) return 'Amanhã';
    if (diffDays === -1) return 'Ontem';
    if (diffDays > 1) return `Em ${diffDays} dias`;
    return `Há ${Math.abs(diffDays)} dias`;
  } catch {
    return '';
  }
}

const EventModal: React.FC<EventModalProps> = ({ event, onClose }) => {
  const { isDone, toggleDone } = useDoneEvents();

  useEffect(() => {
    if (!event) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleEsc);
      document.body.style.overflow = '';
    };
  }, [event, onClose]);

  if (!event) return null;

  const type = event.type as EventType;
  const past = (() => {
    const d = new Date(`${event.date}T23:59:59`).getTime();
    return !isNaN(d) && d < Date.now();
  })();
  const done = isDone(event);

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="modal-close"
          onClick={onClose}
          aria-label="Fechar"
        >
          ×
        </button>

        <div className="modal-header">
          <span className={`badge ${TYPE_BADGES[type] ?? 'badge--other'}`}>
            {TYPE_LABELS[type] ?? type}
          </span>
          {done && <span className="status-pill status-pill--done">✓ Concluído</span>}
          {past && !done && <span className="status-pill status-pill--past">Encerrado</span>}
          {event.synced && (
            <span className="status-pill status-pill--synced">📅 Sincronizado</span>
          )}
        </div>

        <h2 className="modal-title">{event.title}</h2>

        <div className="modal-date-block">
          <div className="modal-date-block__main">
            📆 {formatFullDate(event.date, event.time)}
          </div>
          {!past && (
            <div className="modal-date-block__relative">{relativeDays(event.date, event.time)}</div>
          )}
        </div>

        <div className="modal-meta">
          <span>📚 {event.subject}</span>
          {event.time && <span>🕐 {event.time}</span>}
        </div>

        {event.description && (
          <div className="modal-description">
            {event.description.split('\n').map((line, i) => (
              <p key={i}>{renderLineWithLinks(line)}</p>
            ))}
          </div>
        )}

        <div className="modal-actions">
          {event.url && (
            <a
              href={event.url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary"
              title="Abrir no portal UNOESC (em nova aba)"
            >
              🔗 Abrir no portal
            </a>
          )}
          <button
            type="button"
            className={done ? 'btn-secondary' : 'btn-done'}
            onClick={() => toggleDone(event)}
          >
            {done ? '↺ Marcar como pendente' : '✓ Marcar como concluído'}
          </button>
        </div>
      </div>
    </div>
  );
};

/** Renderiza uma linha de texto convertendo URLs em links clicáveis. */
function renderLineWithLinks(line: string): React.ReactNode {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const parts = line.split(urlRegex);
  return parts.map((part, i) =>
    urlRegex.test(part) ? (
      <a key={i} href={part} target="_blank" rel="noopener noreferrer">
        {part}
      </a>
    ) : (
      <React.Fragment key={i}>{part}</React.Fragment>
    ),
  );
}

export default EventModal;
