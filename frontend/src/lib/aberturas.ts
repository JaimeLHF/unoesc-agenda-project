import type { AcademicEvent } from '../types';

/*
  O Moodle cria dois eventos para a mesma prova: "Início de X", quando abre, e
  "Término de X", quando fecha. Na agenda eram duas linhas para uma coisa só, e
  a de cima parecia o prazo — em 26/09/2026 "EM 2 DIAS: Prova" era a Avaliativa
  3 abrindo, não vencendo. Quando os dois existem, fica o prazo, carregando a
  abertura em `abre`; abertura sem par continua sozinha.

  Roda antes de qualquer tela, e não dentro de cada uma: faixa, semana,
  disciplina e contagem de carga precisam enxergar a mesma lista.
*/

const PREFIXO = /^(in[ií]cio|abertura|t[eé]rmino|fechamento|encerramento)\s+d[eoa]s?\s+/i;

/** "Início de X" e "Término de X" viram a mesma chave dentro da disciplina. */
function chavePar(ev: AcademicEvent): string {
  return `${ev.subject}|${ev.title.replace(PREFIXO, '').trim().toLowerCase()}`;
}

export function juntarAberturas(events: AcademicEvent[]): AcademicEvent[] {
  const aberturas = new Map<string, AcademicEvent>();
  for (const ev of events) {
    if (ev.event_type === 'open') aberturas.set(chavePar(ev), ev);
  }
  if (aberturas.size === 0) return events;

  const usadas = new Set<AcademicEvent>();
  const prazos = events.map((ev) => {
    if (ev.event_type !== 'close' && ev.event_type !== 'due') return ev;
    const abertura = aberturas.get(chavePar(ev));
    if (!abertura) return ev;
    usadas.add(abertura);
    return { ...ev, abre: { date: abertura.date, time: abertura.time } };
  });
  return prazos.filter((ev) => !usadas.has(ev));
}

/** "28/09", enquanto a abertura não chegou; depois dela, nada a dizer. */
export function aberturaFutura(ev: AcademicEvent): string | null {
  if (!ev.abre) return null;
  const quando = new Date(`${ev.abre.date}T${ev.abre.time ?? '00:00'}:00`).getTime();
  if (isNaN(quando) || quando <= Date.now()) return null;
  const [, m, d] = ev.abre.date.split('-');
  return `${d}/${m}`;
}
