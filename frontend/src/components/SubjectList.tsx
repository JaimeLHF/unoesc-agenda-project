import React from 'react';
import type { Subject, AcademicEvent, EventType } from '../types';
import EventAlerts from './EventAlerts';
import Icon from './Icon';
import { useDoneEvents } from '../contexts/DoneEventsContext';

interface SubjectListProps {
  subjects: Subject[];
  events: AcademicEvent[];
  onSelectSubject: (id: string) => void;
  /** Só para avisar que os números na tela podem mudar em instantes. */
  refreshing: boolean;
  lastScrapedAt?: string | null;
  /** Repassado para a faixa de alertas, que leva à página da atividade. */
  onOpenEvent: (event: AcademicEvent) => void;
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

/**
 * Separa "28743 - Desenvolvimento Mobile" em código e nome. Sem o padrão
 * esperado, devolve o texto inteiro como nome — nome de disciplina vem do
 * Moodle e nem toda instituição usa o mesmo formato.
 */
function splitSubjectName(fullName: string): { code: string | null; label: string } {
  const match = fullName.match(/^(\d{3,})\s*-\s*(.+)$/);
  return match ? { code: match[1], label: match[2] } : { code: null, label: fullName };
}

/**
 * Período letivo ("2026/2") a que a disciplina pertence.
 *
 * Não use `end_date`: no Moodle da UNOESC ele é a data em que a *sala* fecha,
 * meses depois do componente terminar — Engenharia de Software acabou em
 * 12/07/2026 e a sala só fecha em 10/09. `start_date` é confiável, mas vem 7
 * dias antes do início oficial (é quando o Moodle libera o acesso), então os
 * 7 dias voltam antes de olhar o mês. Sem data, devolve null e a disciplina
 * conta como do semestre corrente.
 */
function academicTerm(subject: Subject): { year: number; half: 1 | 2 } | null {
  if (!subject.start_date) return null;
  const inicio = new Date((subject.start_date + 7 * 24 * 3600) * 1000);
  return { year: inicio.getFullYear(), half: inicio.getMonth() < 6 ? 1 : 2 };
}

function currentTerm(now: Date): { year: number; half: 1 | 2 } {
  return { year: now.getFullYear(), half: now.getMonth() < 6 ? 1 : 2 };
}

function termLabel(term: { year: number; half: 1 | 2 }): string {
  return `${term.year}/${term.half}`;
}

function termRank(term: { year: number; half: 1 | 2 }): number {
  return term.year * 10 + term.half;
}

/**
 * O total do curso no Moodle vem na escala 0–100, mas cada atividade vale de 0
 * a 10 e é essa a média que o aluno reconhece — 95,00 no relatório é o 9,5 do
 * boletim. Só a nota, sem rótulo: "Aprovado" é decisão da UNOESC e o Moodle
 * não guarda isso em lugar nenhum.
 */
function formatGrade(grade: number): string {
  return (grade / 10).toLocaleString('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 2,
  });
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
  refreshing,
  lastScrapedAt,
  onOpenEvent,
}) => {
  const { isDone } = useDoneEvents();
  const lastScrapedRel = formatRelative(lastScrapedAt);

  /*
    A grade é lida de relance procurando o que vence primeiro. Ordenar por
    nome obrigava o aluno a varrer card por card atrás da data mais próxima —
    então quem tem entrega mais perto sobe. Disciplina sem evento futuro cai
    para o fim, e o desempate é pelo nome para a ordem não dançar a cada
    atualização.
  */
  const cards = React.useMemo(() => {
    const atual = termRank(currentTerm(new Date()));
    return subjects
      .map((subject) => {
        const subjEvents = events.filter((e) => e.subject === subject.name);
        const pendingEvents = subjEvents.filter((e) => !isDone(e));
        const stats = computeStats(pendingEvents);
        const nextAt = stats.nextEvent
          ? new Date(`${stats.nextEvent.date}T${stats.nextEvent.time ?? '00:00'}:00`).getTime()
          : Infinity;
        const term = academicTerm(subject);
        return {
          subject,
          subjEvents,
          stats,
          nextAt: isNaN(nextAt) ? Infinity : nextAt,
          term,
          ended: term !== null && termRank(term) < atual,
        };
      })
      .sort((a, b) =>
        a.nextAt !== b.nextAt
          ? a.nextAt - b.nextAt
          : a.subject.name.localeCompare(b.subject.name, 'pt-BR'),
      );
  }, [subjects, events, isDone]);

  /*
    O Moodle não separa semestres: a matrícula continua ativa depois que o
    componente termina, então a lista vinha com 2026/1 e 2026/2 embaralhados.
    As encerradas descem para uma seção própria — da mais recente para a mais
    antiga, que é a ordem em que o aluno lembra delas.
  */
  const emAndamento = cards.filter((c) => !c.ended);
  const encerradas = cards
    .filter((c) => c.ended)
    .sort((a, b) => (b.subject.start_date ?? 0) - (a.subject.start_date ?? 0));

  const renderCard = ({ subject, subjEvents, stats, term, ended }: (typeof cards)[number]) => {
    // Próximo evento ignora os já concluídos — esses não precisam mais aparecer em destaque
    const { counts, upcomingCount, nextEvent } = stats;
    const total = subjEvents.length;
    const doneInSubject = subjEvents.filter((e) => isDone(e)).length;

    const { code, label } = splitSubjectName(subject.name);

    const breakdown = TYPE_ORDER
      .filter((t) => counts[t] > 0)
      .map((t) => `${counts[t]} ${counts[t] === 1 ? TYPE_LABELS[t].singular : TYPE_LABELS[t].plural}`)
      .join(' · ');

    return (
      <button
        key={subject.id}
        type="button"
        className={`subject-card-large${ended ? ' subject-card-large--ended' : ''}`}
        onClick={() => onSelectSubject(subject.id)}
        disabled={total === 0}
      >
        <div className="subject-card-large__header">
          <span className="subject-card-large__title">
            {/*
              "28743 - Desenvolvimento Mobile" quebrava em três linhas
              tortas porque o código disputava espaço com o nome. Separado,
              o código vira etiqueta e o nome fica legível de relance —
              que é o que o aluno procura ao varrer a grade.
            */}
            {(code || term) && (
              <span className="subject-card-large__code">
                {code}
                {code && term && ' · '}
                {term && termLabel(term)}
              </span>
            )}
            <span className="subject-card-large__name">{label}</span>
          </span>
          <span className="subject-card-large__badges">
            {typeof subject.final_grade === 'number' && (
              <span className="subject-card-large__grade">
                Nota {formatGrade(subject.final_grade)}
              </span>
            )}
            <span className="subject-card-large__total">
              {total} {total === 1 ? 'evento' : 'eventos'}
            </span>
          </span>
        </div>

        {total > 0 ? (
          <>
            <div className="subject-card-large__breakdown">{breakdown}</div>
            {doneInSubject > 0 && (
              <div className="subject-card-large__done">
                <Icon name="check" size={0.95} />
                {doneInSubject} de {total} concluído{doneInSubject === 1 ? '' : 's'}
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
  };

  return (
    <section className="subject-grid-section">
      <div className="page-heading">
        <h2 className="section-title">Suas disciplinas</h2>
        <p className="section-subtitle">
          Clique em uma disciplina para ver os eventos dela.
          {refreshing
            ? ' · Buscando dados novos no Moodle…'
            : lastScrapedRel && ` · Atualizado ${lastScrapedRel}`}
        </p>
      </div>

      <EventAlerts events={events} onOpenEvent={onOpenEvent} />

      {subjects.length === 0 ? (
        <div className="empty-state">Nenhuma disciplina encontrada no portal.</div>
      ) : (
        <>
          {emAndamento.length > 0 && (
            <div className="subject-grid-large">{emAndamento.map(renderCard)}</div>
          )}

          {encerradas.length > 0 && (
            <>
              <div className="subject-group-heading">
                <h3 className="subject-group-heading__title">Encerradas</h3>
                <p className="subject-group-heading__hint">
                  Semestres anteriores — o Moodle mantém a sala aberta depois que o componente termina.
                </p>
              </div>
              <div className="subject-grid-large">{encerradas.map(renderCard)}</div>
            </>
          )}
        </>
      )}
    </section>
  );
};

export default SubjectList;
