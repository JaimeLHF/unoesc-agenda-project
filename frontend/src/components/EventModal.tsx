import React, { useEffect, useState } from 'react';
import type { AcademicEvent, EventType } from '../types';
import { useDoneEvents } from '../contexts/DoneEventsContext';

interface EventModalProps {
  event: AcademicEvent | null;
  onClose: () => void;
  onOpenPortal?: (subjectName: string, targetUrl?: string) => Promise<{ ssoUrl: string; targetUrl?: string } | null>;
  onAskAi?: (event: AcademicEvent) => void;
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

const EventModal: React.FC<EventModalProps> = ({ event, onClose, onOpenPortal, onAskAi }) => {
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
              title="Fazer login automático e abrir a atividade no Moodle"
              onClick={async () => {
                // Abre a janela imediatamente no clique (evita bloqueio de popup)
                const newTab = window.open('about:blank', '_blank');
                setOpeningPortal(true);
                try {
                  const result = await onOpenPortal(event.subject, event.url);
                  if (result && newTab) {
                    // Mostra loading enquanto o SSO carrega
                    newTab.document.write(`
                      <html>
                        <head><title>Abrindo atividade...</title></head>
                        <body style="margin:0;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui,sans-serif;background:#f8f9fa;">
                          <div style="text-align:center;">
                            <div style="width:40px;height:40px;border:4px solid #e0e0e0;border-top-color:#4f46e5;border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 16px;"></div>
                            <p style="color:#374151;font-size:16px;margin:0;">Fazendo login e abrindo a atividade…</p>
                            <p style="color:#6b7280;font-size:13px;margin-top:8px;">Aguarde alguns segundos.</p>
                          </div>
                          <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
                        </body>
                      </html>
                    `);
                    newTab.document.close();

                    if (result.targetUrl) {
                      newTab.location.href = result.ssoUrl;
                      setTimeout(() => {
                        newTab.location.href = result.targetUrl!;
                      }, 3000);
                    } else {
                      newTab.location.href = result.ssoUrl;
                    }
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
              {openingPortal ? '⏳ Abrindo…' : '🔗 Abrir no portal'}
            </button>
          )}
          <button
            type="button"
            className={done ? 'btn-secondary' : 'btn-done'}
            onClick={() => toggleDone(event)}
          >
            {done ? '↺ Marcar como pendente' : '✓ Marcar como concluído'}
          </button>
          {onAskAi && event.url && (
            <button
              type="button"
              className="btn-ai"
              onClick={() => onAskAi(event)}
              title="Pedir ajuda à IA para resolver esta atividade"
            >
              🤖 Pedir ajuda à IA
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

/** Remove espaços/tabs/nbsp do início e colapsa whitespace após bullets. */
function normalizeLine(line: string): string {
  const trimmed = line.replace(/^[\s ]+/, '');
  return trimmed.replace(/^([·•\-*])[\s ]+/, '$1 ');
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
