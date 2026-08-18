import React from 'react';
import type { AcademicEvent, EventType } from '../types';
import { useDoneEvents } from '../contexts/DoneEventsContext';
import Icon from './Icon';

interface NextDeadlineProps {
  events: AcademicEvent[];
  onOpenEvent: (event: AcademicEvent) => void;
}

const TIPO: Record<EventType, string> = {
  webconference: 'Webconferência',
  deadline: 'Entrega',
  exam: 'Prova',
  other: 'Evento',
};

/**
 * Janela da barra: 14 dias. Além disso ela ficaria quase cheia todo dia e
 * pararia de dizer qualquer coisa — o encurtamento só se sente quando o
 * intervalo é curto o bastante para caber na semana do aluno.
 */
const JANELA_DIAS = 14;
const DIA = 24 * 60 * 60 * 1000;

function quando(event: AcademicEvent): number {
  return new Date(`${event.date}T${event.time ?? '23:59'}:59`).getTime();
}

/** "faltam 3 dias", "faltam 5 horas" — a unidade acompanha a urgência. */
function faltaTexto(ms: number): string {
  const horas = Math.floor(ms / (60 * 60 * 1000));
  if (horas < 1) return 'falta menos de uma hora';
  if (horas < 24) return `${horas === 1 ? 'falta 1 hora' : `faltam ${horas} horas`}`;
  const dias = Math.round(horas / 24);
  return dias === 1 ? 'falta 1 dia' : `faltam ${dias} dias`;
}

function dataLegivel(event: AcademicEvent): string {
  const d = new Date(`${event.date}T${event.time ?? '00:00'}:00`);
  const data = d.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' });
  return event.time ? `${data} às ${event.time}` : data;
}

/**
 * O próximo prazo em destaque, com o tempo que resta.
 *
 * Uma data é um número; "faltam 3 dias" é uma sensação. A barra existe pelo
 * mesmo motivo — ela encurta a cada dia, e é isso que faz o aluno olhar de
 * novo amanhã.
 *
 * Mostra só o primeiro pendente: a faixa de alertas logo abaixo continua
 * listando o resto da semana, e dois destaques competindo não destacam nada.
 */
const NextDeadline: React.FC<NextDeadlineProps> = ({ events, onOpenEvent }) => {
  const { isDone } = useDoneEvents();
  const agora = Date.now();

  const proximo = events
    .filter((e) => !isDone(e))
    .map((e) => ({ e, t: quando(e) }))
    .filter(({ t }) => !isNaN(t) && t >= agora)
    .sort((a, b) => a.t - b.t)[0];

  if (!proximo) return null;

  const restante = proximo.t - agora;
  const decorrido = Math.min(1, Math.max(0, 1 - restante / (JANELA_DIAS * DIA)));
  const urgencia = restante < DIA ? 'hoje' : restante < 3 * DIA ? 'perto' : 'calma';
  const tipo = TIPO[proximo.e.type as EventType] ?? 'Evento';

  return (
    <button
      type="button"
      className={`proximo proximo--${urgencia}`}
      onClick={() => onOpenEvent(proximo.e)}
    >
      <div className="proximo__topo">
        <span className="proximo__rotulo">Próximo prazo</span>
        <span className="proximo__falta">{faltaTexto(restante)}</span>
      </div>

      <p className="proximo__titulo">{proximo.e.title}</p>
      <p className="proximo__meta">
        {tipo} · {proximo.e.subject.replace(/^\d+\s*-\s*/, '')}
      </p>

      <div className="proximo__barra" aria-hidden="true">
        <span className="proximo__barra-preenchida" style={{ width: `${decorrido * 100}%` }} />
      </div>

      <p className="proximo__data">
        <Icon name="relogio" size={0.9} />
        {dataLegivel(proximo.e)}
      </p>
    </button>
  );
};

export default NextDeadline;
