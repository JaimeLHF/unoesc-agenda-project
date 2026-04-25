import React, { useState } from 'react';
import type { AcademicEvent, EventType } from '../types';
import EventModal from './EventModal';
import { useDoneEvents } from '../contexts/DoneEventsContext';

interface EventAlertsProps {
  events: AcademicEvent[];
  maxAlerts?: number;
}

type Urgency = 'today' | 'tomorrow' | 'soon' | 'week';

interface Alert {
  event: AcademicEvent;
  urgency: Urgency;
  diffDays: number;
}

/** Substantivos por tipo, em letra minúscula para uso em frase. */
const TYPE_NOUN: Record<EventType, string> = {
  webconference: 'Webconferência',
  deadline: 'Entrega',
  exam: 'Prova',
  other: 'Evento',
};

/** Calcula urgência (em dias civis) e filtra apenas eventos futuros. */
function computeAlerts(events: AcademicEvent[]): Alert[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayMs = today.getTime();

  const alerts: Alert[] = [];
  for (const ev of events) {
    let eventTime: number;
    try {
      eventTime = new Date(`${ev.date}T${ev.time ?? '23:59'}:59`).getTime();
    } catch {
      continue;
    }
    if (isNaN(eventTime) || eventTime < Date.now()) continue;

    const eventDay = new Date(`${ev.date}T00:00:00`).getTime();
    const diffDays = Math.round((eventDay - todayMs) / (1000 * 60 * 60 * 24));
    if (diffDays < 0 || diffDays > 7) continue;

    let urgency: Urgency;
    if (diffDays === 0) urgency = 'today';
    else if (diffDays === 1) urgency = 'tomorrow';
    else if (diffDays <= 3) urgency = 'soon';
    else urgency = 'week';

    alerts.push({ event: ev, urgency, diffDays });
  }

  alerts.sort((a, b) => {
    if (a.diffDays !== b.diffDays) return a.diffDays - b.diffDays;
    return (a.event.time ?? '').localeCompare(b.event.time ?? '');
  });
  return alerts;
}

function buildMessage(alert: Alert): { icon: string; text: string } {
  const { event, urgency, diffDays } = alert;
  const noun = TYPE_NOUN[event.type as EventType] ?? 'Evento';
  const subject = event.subject.replace(/^\d+\s*-\s*/, ''); // tira código numérico do início
  const time = event.time ? ` às ${event.time}` : '';

  switch (urgency) {
    case 'today':
      return {
        icon: '🚨',
        text: `HOJE${time}: ${noun} de ${subject} — fique atento!`,
      };
    case 'tomorrow':
      return {
        icon: '⚠️',
        text: `AMANHÃ${time}: ${noun} de ${subject}`,
      };
    case 'soon':
      return {
        icon: '⏰',
        text: `EM ${diffDays} DIAS: ${noun} de ${subject}`,
      };
    case 'week':
      return {
        icon: '📅',
        text: `EM ${diffDays} DIAS: ${noun} de ${subject}`,
      };
  }
}

const EventAlerts: React.FC<EventAlertsProps> = ({ events, maxAlerts = 6 }) => {
  const [openEvent, setOpenEvent] = useState<AcademicEvent | null>(null);
  const { isDone } = useDoneEvents();

  // Eventos já marcados como concluídos não geram alertas — o aluno já os fez
  const pending = events.filter((e) => !isDone(e));
  const alerts = computeAlerts(pending).slice(0, maxAlerts);
  if (alerts.length === 0) return null;

  return (
    <section className="alerts-section" aria-label="Eventos urgentes">
      <h3 className="alerts-title">
        🔔 Próximos eventos
        <span className="alerts-count">({alerts.length})</span>
      </h3>
      <ul className="alerts-list">
        {alerts.map((alert) => {
          const { icon, text } = buildMessage(alert);
          return (
            <li key={alert.event.id}>
              <button
                type="button"
                className={`alert-pill alert-pill--${alert.urgency}`}
                onClick={() => setOpenEvent(alert.event)}
                title={alert.event.title}
              >
                <span className="alert-pill__icon">{icon}</span>
                <span className="alert-pill__text">{text}</span>
                <span className="alert-pill__title">{alert.event.title}</span>
              </button>
            </li>
          );
        })}
      </ul>

      <EventModal event={openEvent} onClose={() => setOpenEvent(null)} />
    </section>
  );
};

export default EventAlerts;
