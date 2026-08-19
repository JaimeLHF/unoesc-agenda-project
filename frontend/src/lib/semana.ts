/**
 * Quanto peso tem uma semana.
 *
 * A informação já estava na tela — os eventos aparecem todos —, mas ninguém lê
 * uma lista contando. O aluno descobria que a semana tinha três entregas e uma
 * prova na terça-feira, quando já não dava para dividir o esforço.
 *
 * Não vira gráfico: o painel de gráficos já foi construído e descartado neste
 * projeto. É uma frase e um selo, no lugar onde a pessoa já está olhando.
 */
import type { AcademicEvent, EventType } from '../types';

/**
 * A partir de quantos compromissos a semana é "cheia".
 *
 * Três é o número em que a semana deixa de caber num fim de semana. Abaixo
 * disso o aviso apareceria quase toda semana e viraria paisagem — o mesmo
 * motivo pelo qual os selos de prazo alterado e nota nova expiram.
 */
export const LIMITE_SEMANA_CHEIA = 3;

/** Duas provas na mesma semana já é semana pesada, mesmo sem mais nada. */
export const LIMITE_PROVAS = 2;

export interface CargaDaSemana {
  total: number;
  provas: number;
  webconferencias: number;
  entregas: number;
  /** O dia com mais compromissos, quando ele concentra mais de um. */
  diaMaisCheio: { data: string; quantidade: number } | null;
  cheia: boolean;
}

const DIA_MS = 24 * 60 * 60 * 1000;

/** "2026-08-19" a partir de um Date local, sem passar por UTC. */
export function chaveDoDia(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`;
}

/**
 * Soma os compromissos de um intervalo de dias (limites incluídos).
 *
 * `estaFeito` entra como função porque o que já foi entregue não pesa mais —
 * marcar como concluído é justamente o aluno dizendo "esse eu resolvi".
 */
export function cargaDaSemana(
  eventos: AcademicEvent[],
  primeiroDia: Date,
  dias: number,
  estaFeito: (e: AcademicEvent) => boolean,
): CargaDaSemana {
  const inicio = chaveDoDia(primeiroDia);
  const fim = chaveDoDia(new Date(primeiroDia.getTime() + (dias - 1) * DIA_MS));

  const contagem: Record<EventType, number> = {
    exam: 0,
    deadline: 0,
    webconference: 0,
    other: 0,
  };
  const porDia = new Map<string, number>();

  for (const e of eventos) {
    if (e.date < inicio || e.date > fim || estaFeito(e)) continue;
    contagem[e.type as EventType] = (contagem[e.type as EventType] ?? 0) + 1;
    porDia.set(e.date, (porDia.get(e.date) ?? 0) + 1);
  }

  const total = contagem.exam + contagem.deadline + contagem.webconference + contagem.other;

  let diaMaisCheio: CargaDaSemana['diaMaisCheio'] = null;
  for (const [data, quantidade] of porDia) {
    if (quantidade > 1 && (!diaMaisCheio || quantidade > diaMaisCheio.quantidade)) {
      diaMaisCheio = { data, quantidade };
    }
  }

  return {
    total,
    provas: contagem.exam,
    webconferencias: contagem.webconference,
    entregas: contagem.deadline + contagem.other,
    diaMaisCheio,
    cheia: total >= LIMITE_SEMANA_CHEIA || contagem.exam >= LIMITE_PROVAS,
  };
}

/** "2 provas e 1 entrega" — só o que existe, na ordem do que pesa mais. */
export function descreverCarga(carga: CargaDaSemana): string {
  const partes: string[] = [];
  if (carga.provas) partes.push(`${carga.provas} ${carga.provas === 1 ? 'prova' : 'provas'}`);
  if (carga.entregas)
    partes.push(`${carga.entregas} ${carga.entregas === 1 ? 'entrega' : 'entregas'}`);
  if (carga.webconferencias)
    partes.push(
      `${carga.webconferencias} ${
        carga.webconferencias === 1 ? 'webconferência' : 'webconferências'
      }`,
    );

  if (partes.length === 0) return 'nada marcado';
  if (partes.length === 1) return partes[0];
  return `${partes.slice(0, -1).join(', ')} e ${partes[partes.length - 1]}`;
}

/**
 * "terça-feira, 25 de ago" — o dia em que a semana aperta.
 *
 * O ponto final do mês abreviado sai: quem chama põe o dele, e "ago.." é o
 * tipo de detalhe que faz a frase parecer gerada por máquina.
 */
export function nomeDoDia(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  if (isNaN(d.getTime())) return iso;
  return d
    .toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'short' })
    .replace(/\.$/, '');
}
