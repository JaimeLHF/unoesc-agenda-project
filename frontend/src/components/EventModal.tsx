import React, { useEffect, useState } from 'react';
import type { AcademicEvent, EventType } from '../types';
import Icon from './Icon';
import { useDoneEvents } from '../contexts/DoneEventsContext';

interface EventModalProps {
  event: AcademicEvent | null;
  onClose: () => void;
  onOpenPortal?: (subjectName: string, targetUrl?: string) => Promise<string | null>;
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
    // "domingo, 16 de agosto…" → "Domingo, 16 de agosto…". Em CSS isso seria
    // `capitalize`, que sobe também o "De" de cada preposição.
    const capitalizado = dateStr.charAt(0).toUpperCase() + dateStr.slice(1);
    return time ? `${capitalizado} às ${time}` : capitalizado;
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

const EventModal: React.FC<EventModalProps> = ({ event, onClose, onOpenPortal }) => {
  const { isDone, toggleDone } = useDoneEvents();
  const [openingPortal, setOpeningPortal] = useState(false);

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
        <button type="button" className="modal-close" onClick={onClose}>
          <Icon name="fechar" label="Fechar" />
        </button>

        <div className="modal-header">
          <span className={`badge ${TYPE_BADGES[type] ?? 'badge--other'}`}>
            {TYPE_LABELS[type] ?? type}
          </span>
          {done && (
            <span className="status-pill status-pill--done">
              <Icon name="check" size={0.9} /> Concluído
            </span>
          )}
          {past && !done && <span className="status-pill status-pill--past">Encerrado</span>}
          {event.synced && (
            <span className="status-pill status-pill--synced">
              <Icon name="calendario" size={0.9} /> Sincronizado
            </span>
          )}
        </div>

        <h2 className="modal-title">{event.title}</h2>

        <div className="modal-date-block">
          <div className="modal-date-block__main">
            <Icon name="calendario" />
            {formatFullDate(event.date, event.time)}
          </div>
          {!past && (
            <div className="modal-date-block__relative">{relativeDays(event.date, event.time)}</div>
          )}
        </div>

        <div className="modal-meta">
          <span>
            <Icon name="prova" size={1} />
            {event.subject}
          </span>
          {event.time && (
            <span>
              <Icon name="relogio" size={1} />
              {event.time}
            </span>
          )}
        </div>

        {event.description && (
          <div className="modal-description">
            {event.description.split('\n').map((line, i) => (
              <p key={i}>{renderLineWithLinks(normalizeLine(line))}</p>
            ))}
          </div>
        )}

        <div className="modal-actions">
          {onOpenPortal && (
            <button
              type="button"
              className="btn-secondary"
              disabled={openingPortal}
              title="Abrir a atividade no Moodle"
              onClick={async () => {
                // A aba é aberta no próprio clique para o navegador não tratar
                // como popup — o link só chega depois, na resposta do backend.
                const newTab = window.open('about:blank', '_blank');
                setOpeningPortal(true);
                try {
                  const url = await onOpenPortal(event.subject, event.url);
                  if (url && newTab) {
                    newTab.location.href = url;
                  } else {
                    newTab?.close();
                  }
                } catch {
                  newTab?.close();
                } finally {
                  setOpeningPortal(false);
                }
              }}
            >
              {openingPortal ? (
                <>
                  <span className="spinner spinner--dark" aria-hidden="true" /> Abrindo…
                </>
              ) : (
                <>
                  <Icon name="link-externo" /> Abrir no Moodle
                </>
              )}
            </button>
          )}
          <button
            type="button"
            className={done ? 'btn-secondary' : 'btn-done'}
            onClick={() => toggleDone(event)}
          >
            {done ? (
              <>
                <Icon name="desfazer" /> Marcar como pendente
              </>
            ) : (
              <>
                <Icon name="check" /> Marcar como concluído
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

/** Remove espaços/tabs/nbsp do início e colapsa whitespace após bullets. */
function normalizeLine(line: string): string {
  const trimmed = line.replace(/^[\s\u00A0]+/, '');
  return trimmed.replace(/^([·•\-*])[\s\u00A0]+/, '$1 ');
}

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
