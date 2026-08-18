import React, { useState } from 'react';
import type { AcademicEvent, EventType } from '../types';
import { useDoneEvents } from '../contexts/DoneEventsContext';
import Icon from './Icon';

interface WeekViewProps {
  events: AcademicEvent[];
  onOpenEvent: (event: AcademicEvent) => void;
}

const DIA = 24 * 60 * 60 * 1000;
const NOMES = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];

const TIPO_ICONE: Record<EventType, 'video' | 'entrega' | 'prova' | 'pin'> = {
  webconference: 'video',
  deadline: 'entrega',
  exam: 'prova',
  other: 'pin',
};

function inicioDaSemana(d: Date): Date {
  const data = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  // getDay(): 0 = domingo. A semana da faculdade começa na segunda.
  return new Date(data.getTime() - ((data.getDay() + 6) % 7) * DIA);
}

function chaveDoDia(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`;
}

function intervalo(inicio: Date): string {
  const fim = new Date(inicio.getTime() + 6 * DIA);
  const fmt = (d: Date) => d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
  return `${fmt(inicio)} – ${fmt(fim)}`;
}

/**
 * A semana do aluno, de segunda a domingo.
 *
 * O app organiza tudo por disciplina, que é como o Moodle guarda; a cabeça de
 * quem estuda organiza por dia — "o que eu tenho essa semana?" é a pergunta
 * que ninguém consegue responder olhando seis cartões de disciplina.
 *
 * Dia sem nada aparece assim mesmo, vazio: o buraco na semana é informação —
 * é onde dá para adiantar o que vence na semana seguinte.
 */
const WeekView: React.FC<WeekViewProps> = ({ events, onOpenEvent }) => {
  const [offset, setOffset] = useState(0);
  const { isDone } = useDoneEvents();

  const hoje = new Date();
  const primeira = new Date(inicioDaSemana(hoje).getTime() + offset * 7 * DIA);
  const hojeChave = chaveDoDia(hoje);

  const porDia = new Map<string, AcademicEvent[]>();
  for (const e of events) {
    const lista = porDia.get(e.date) ?? [];
    lista.push(e);
    porDia.set(e.date, lista);
  }

  const dias = Array.from({ length: 7 }, (_, i) => {
    const data = new Date(primeira.getTime() + i * DIA);
    const chave = chaveDoDia(data);
    const doDia = (porDia.get(chave) ?? []).sort((a, b) =>
      (a.time ?? '').localeCompare(b.time ?? ''),
    );
    return { data, chave, nome: NOMES[i], eventos: doDia };
  });

  const vazia = dias.every((d) => d.eventos.length === 0);

  return (
    <section className="semana">
      <div className="semana__topo">
        <div>
          <h3 className="semana__titulo">
            {offset === 0 ? 'Esta semana' : offset === 1 ? 'Semana que vem' : intervalo(primeira)}
          </h3>
          <p className="semana__intervalo">{intervalo(primeira)}</p>
        </div>
        <div className="semana__nav">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => setOffset((o) => o - 1)}
            aria-label="Semana anterior"
          >
            <Icon name="voltar" size={0.9} />
          </button>
          {offset !== 0 && (
            <button type="button" className="btn-ghost" onClick={() => setOffset(0)}>
              Hoje
            </button>
          )}
          <button
            type="button"
            className="btn-ghost semana__nav-proxima"
            onClick={() => setOffset((o) => o + 1)}
            aria-label="Próxima semana"
          >
            <Icon name="voltar" size={0.9} />
          </button>
        </div>
      </div>

      {vazia && <p className="semana__vazia">Nada marcado nesta semana.</p>}

      <div className="semana__grade">
        {dias.map(({ data, chave, nome, eventos }) => (
          <div
            key={chave}
            className={`semana__dia${chave === hojeChave ? ' semana__dia--hoje' : ''}`}
          >
            <div className="semana__cabecalho">
              <span className="semana__nome">{nome}</span>
              <span className="semana__numero">{data.getDate()}</span>
            </div>

            {eventos.length === 0 ? (
              <p className="semana__livre">livre</p>
            ) : (
              <ul className="semana__eventos">
                {eventos.map((e) => (
                  <li key={e.id}>
                    <button
                      type="button"
                      className={`semana__evento semana__evento--${e.type}${
                        isDone(e) ? ' semana__evento--feito' : ''
                      }`}
                      onClick={() => onOpenEvent(e)}
                      title={`${e.title} — ${e.subject}`}
                    >
                      <Icon name={TIPO_ICONE[e.type as EventType] ?? 'pin'} size={0.85} />
                      <span className="semana__evento-texto">
                        {e.time && <span className="semana__hora">{e.time}</span>}
                        {e.title}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </section>
  );
};

export default WeekView;
