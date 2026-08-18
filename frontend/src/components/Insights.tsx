import React from 'react';
import type { AcademicEvent, EventType, Subject } from '../types';

/**
 * Três leituras da agenda que o cartão sozinho não dá: como o trabalho se
 * distribui nas próximas semanas, quanto cada disciplina ainda cobra, e como
 * foram as notas dos semestres que já fecharam.
 *
 * Tudo desenhado em SVG à mão, sem biblioteca: o público abre isso no 4G e o
 * projeto não aceita dependência nova no frontend sem um bom motivo.
 *
 * As cores das séries vivem em `index.css` (`--chart-*`), uma paleta por tema,
 * validada para daltonismo — e nenhuma delas é a única pista: a legenda e os
 * rótulos dizem o mesmo em texto.
 */

interface InsightsProps {
  subjects: Subject[];
  events: AcademicEvent[];
  /** Nota mínima de aprovação, na escala 0–10. Vem da tela de disciplinas. */
  mediaAprovacao: number;
}

const SERIES: { type: EventType; label: string; cor: string }[] = [
  { type: 'deadline', label: 'Entregas', cor: 'var(--chart-entrega)' },
  { type: 'exam', label: 'Provas', cor: 'var(--chart-prova)' },
  { type: 'webconference', label: 'Webconferências', cor: 'var(--chart-webconf)' },
];

const SEMANAS = 8;
const DIA = 24 * 60 * 60 * 1000;

function inicioDaSemana(d: Date): Date {
  const data = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  // getDay(): 0 = domingo. A semana do aluno começa na segunda.
  const desloca = (data.getDay() + 6) % 7;
  return new Date(data.getTime() - desloca * DIA);
}

function dataDoEvento(e: AcademicEvent): number {
  return new Date(`${e.date}T${e.time ?? '00:00'}:00`).getTime();
}

function rotuloSemana(inicio: Date): string {
  return inicio.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

/** Quantos eventos de cada tipo caem em cada uma das próximas 8 semanas. */
function porSemana(events: AcademicEvent[], hoje: Date) {
  const primeira = inicioDaSemana(hoje);
  const semanas = Array.from({ length: SEMANAS }, (_, i) => ({
    inicio: new Date(primeira.getTime() + i * 7 * DIA),
    counts: { deadline: 0, exam: 0, webconference: 0, other: 0 } as Record<EventType, number>,
    total: 0,
  }));

  for (const e of events) {
    const t = dataDoEvento(e);
    if (isNaN(t)) continue;
    const indice = Math.floor((t - primeira.getTime()) / (7 * DIA));
    if (indice < 0 || indice >= SEMANAS) continue;
    semanas[indice].counts[e.type as EventType] += 1;
    semanas[indice].total += 1;
  }
  return semanas;
}

/** Barras empilhadas: uma coluna por semana, uma cor por tipo de evento. */
const MapaDasSemanas: React.FC<{ events: AcademicEvent[] }> = ({ events }) => {
  const hoje = new Date();
  const semanas = porSemana(events, hoje);
  const maior = Math.max(1, ...semanas.map((s) => s.total));
  const vazio = semanas.every((s) => s.total === 0);

  const L = 26; // espaço da escala à esquerda
  const W = 320;
  const H = 130;
  const base = H - 22;
  const largura = (W - L) / SEMANAS;
  const barra = largura - 8;

  if (vazio) {
    return <p className="chart__empty">Nada marcado nas próximas oito semanas.</p>;
  }

  return (
    <svg
      className="chart__svg"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Eventos por semana nas próximas oito semanas"
    >
      {/* Duas linhas de referência bastam: o valor exato está no tooltip. */}
      {[0, maior].map((v) => (
        <g key={v}>
          <line
            x1={L}
            x2={W}
            y1={base - (v / maior) * (base - 12)}
            y2={base - (v / maior) * (base - 12)}
            className="chart__grid"
          />
          <text x={0} y={base - (v / maior) * (base - 12) + 3} className="chart__tick">
            {v}
          </text>
        </g>
      ))}

      {semanas.map((s, i) => {
        let y = base;
        return (
          <g key={i}>
            {SERIES.map(({ type, label, cor }) => {
              const n = s.counts[type];
              if (!n) return null;
              const altura = (n / maior) * (base - 12);
              y -= altura;
              return (
                <rect
                  key={type}
                  x={L + i * largura + 4}
                  // O vão de 2px entre segmentos é o que separa duas cores
                  // vizinhas sem precisar de borda.
                  y={y + 1}
                  width={barra}
                  height={Math.max(0, altura - 2)}
                  rx={2}
                  fill={cor}
                >
                  <title>{`${rotuloSemana(s.inicio)}: ${n} ${label.toLowerCase()}`}</title>
                </rect>
              );
            })}
            <text x={L + i * largura + largura / 2} y={H - 6} className="chart__label">
              {rotuloSemana(s.inicio)}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

/** Barras horizontais: quanto cada disciplina ainda cobra daqui para a frente. */
const CargaPorDisciplina: React.FC<{ events: AcademicEvent[] }> = ({ events }) => {
  const agora = Date.now();
  const porDisciplina = new Map<string, number>();
  for (const e of events) {
    const t = dataDoEvento(e);
    if (isNaN(t) || t < agora) continue;
    porDisciplina.set(e.subject, (porDisciplina.get(e.subject) ?? 0) + 1);
  }

  const linhas = [...porDisciplina.entries()].sort((a, b) => b[1] - a[1]);
  if (linhas.length === 0) {
    return <p className="chart__empty">Nenhum prazo à frente.</p>;
  }

  const maior = Math.max(...linhas.map(([, n]) => n));
  return (
    <ul className="chart__bars">
      {linhas.map(([nome, n]) => (
        <li key={nome} className="chart__bar-row">
          <span className="chart__bar-label" title={nome}>
            {nome}
          </span>
          <span className="chart__bar-track">
            <span
              className="chart__bar-fill"
              style={{ width: `${(n / maior) * 100}%` }}
              aria-hidden="true"
            />
          </span>
          <span className="chart__bar-value">{n}</span>
        </li>
      ))}
    </ul>
  );
};

/** Notas das disciplinas já encerradas, com a linha de corte da aprovação. */
const NotasPorSemestre: React.FC<{
  subjects: Subject[];
  mediaAprovacao: number;
}> = ({ subjects, mediaAprovacao }) => {
  const comNota = subjects
    .filter((s) => typeof s.final_grade === 'number')
    .map((s) => ({ nome: s.name, nota: (s.final_grade as number) / 10 }))
    .sort((a, b) => b.nota - a.nota);

  if (comNota.length === 0) {
    return <p className="chart__empty">Nenhuma nota lançada ainda.</p>;
  }

  const media = comNota.reduce((soma, d) => soma + d.nota, 0) / comNota.length;

  return (
    <>
      <p className="chart__hero">
        {media.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
        <span className="chart__hero-label">média das encerradas</span>
      </p>
      <ul className="chart__bars">
        {comNota.map((d) => (
          <li key={d.nome} className="chart__bar-row">
            <span className="chart__bar-label" title={d.nome}>
              {d.nome}
            </span>
            <span className="chart__bar-track">
              {/* A linha de corte fica sobre a trilha: sem ela, uma barra de 6,9
                  parece tão boa quanto uma de 7,1. */}
              <span
                className="chart__bar-cut"
                style={{ left: `${mediaAprovacao * 10}%` }}
                aria-hidden="true"
              />
              <span
                className={`chart__bar-fill chart__bar-fill--${
                  d.nota >= mediaAprovacao ? 'ok' : 'ruim'
                }`}
                style={{ width: `${d.nota * 10}%` }}
                aria-hidden="true"
              />
            </span>
            <span className="chart__bar-value">
              {d.nota.toLocaleString('pt-BR', {
                minimumFractionDigits: 1,
                maximumFractionDigits: 1,
              })}
            </span>
          </li>
        ))}
      </ul>
      <p className="chart__foot">Linha tracejada: nota mínima para aprovação ({mediaAprovacao},0).</p>
    </>
  );
};

const Insights: React.FC<InsightsProps> = ({ subjects, events, mediaAprovacao }) => {
  const temNota = subjects.some((s) => typeof s.final_grade === 'number');

  return (
    <section className="insights">
      {/* Sem a linha divisória do grupo: aqui é o começo da tela, não uma
          separação entre duas listas. */}
      <div className="insights__heading">
        <h3 className="subject-group-heading__title">Panorama</h3>
        <p className="subject-group-heading__hint">
          Os mesmos dados da lista, vistos de longe.
        </p>
      </div>

      <div className="insights__grid">
        <article className="insights__card">
          <h4 className="insights__title">Próximas oito semanas</h4>
          <p className="insights__sub">Quantos compromissos caem em cada semana.</p>
          <MapaDasSemanas events={events} />
          <ul className="chart__legend">
            {SERIES.map(({ type, label, cor }) => (
              <li key={type}>
                <span className="chart__swatch" style={{ background: cor }} aria-hidden="true" />
                {label}
              </li>
            ))}
          </ul>
        </article>

        <article className="insights__card">
          <h4 className="insights__title">Onde estão os prazos</h4>
          <p className="insights__sub">Eventos ainda por vir, por disciplina.</p>
          <CargaPorDisciplina events={events} />
        </article>

        {temNota && (
          <article className="insights__card">
            <h4 className="insights__title">Notas das encerradas</h4>
            <p className="insights__sub">O que o Moodle já lançou.</p>
            <NotasPorSemestre subjects={subjects} mediaAprovacao={mediaAprovacao} />
          </article>
        )}
      </div>
    </section>
  );
};

export default Insights;
