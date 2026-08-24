import type { AcademicEvent, Subject } from '../types';

/*
 * Abrir a agenda deixou de ser esperar pelo Moodle.
 *
 * A regra antiga era "a agenda não abre com o cache": meia agenda velha, numa
 * tela de prazos, é pior que nenhuma, porque o aluno não tem como saber qual
 * metade está velha. O que mudou não foi a regra, foi o que sabemos mostrar —
 * a tela agora diz que está atualizando enquanto atualiza, e anuncia o que
 * chegou quando chega. Com as duas coisas na tela, "qual metade é velha"
 * deixa de ser pergunta sem resposta: nenhuma, e o app avisa quando mudar.
 *
 * Aqui moram as duas decisões dessa troca: quando vale a pena ir ao Moodle de
 * novo, e como dizer o que voltou de lá.
 */

/**
 * Por quanto tempo a agenda recém-buscada é considerada atual.
 *
 * O caso que motivou isto é fechar o app e abrir de novo — no iPhone isso
 * acontece o tempo todo, e cada abertura era um login no Moodle da UNOESC
 * para trazer exatamente os mesmos dados. Quinze minutos é curto o bastante
 * para o prazo publicado de manhã aparecer na primeira olhada do intervalo, e
 * longo o bastante para abrir e fechar três vezes seguidas custar uma busca
 * só. Fora dessa janela a busca acontece, mas por baixo: quem abre o app vê a
 * agenda na hora, atualizada ou não.
 *
 * Isto não é o único caminho de atualização — o botão "Atualizar" ignora a
 * janela, e o push das 7h, 13h e 19h continua entrando pelo servidor.
 */
export const MINUTOS_AGENDA_FRESCA = 15;

/** `true` quando a última busca é recente o bastante para pular a próxima. */
export function agendaEstaFresca(lastScrapedAt?: string | null): boolean {
  if (!lastScrapedAt) return false;

  const quando = new Date(lastScrapedAt).getTime();
  if (Number.isNaN(quando)) return false;

  const minutos = (Date.now() - quando) / 60000;
  // Relógio do aparelho adiantado em relação ao servidor daria minutos
  // negativos, e "no futuro" não é fresco: é motivo para buscar de novo.
  return minutos >= 0 && minutos < MINUTOS_AGENDA_FRESCA;
}

/** Agenda comparável: o que estava na tela antes e o que voltou do Moodle. */
interface Agenda {
  subjects: Subject[];
  events: AcademicEvent[];
}

export interface Novidades {
  /** Eventos que não existiam na agenda anterior. */
  eventos: AcademicEvent[];
  /** Disciplinas que apareceram agora — matrícula nova, semestre que abriu. */
  disciplinas: string[];
  /** O que dizer ao aluno, ou `null` quando não há nada a dizer. */
  frase: string | null;
}

/**
 * Identidade de um evento entre duas buscas.
 *
 * `stable_key` vem do id do Moodle e sobrevive à troca de data — é por isso
 * que o aviso de "Adiado" funciona. Sem ela (prazo lido de PDF, por exemplo)
 * cai no título + disciplina: a data fica de fora de propósito, senão o
 * professor adiar a prova viraria "evento novo".
 */
function chave(e: AcademicEvent): string {
  return e.stable_key || `${e.subject}::${e.title}`;
}

/**
 * O que apareceu entre uma agenda e outra.
 *
 * Só olha o que **surgiu**. Prazo que mudou de data e nota que saiu já têm
 * selo próprio na tela (`previous_date`, `previous_grade`), e repetir isso
 * aqui daria dois avisos para o mesmo fato.
 */
export function compararAgendas(antes: Agenda, depois: Agenda): Novidades {
  const conhecidos = new Set(antes.events.map(chave));
  const eventos = depois.events.filter((e) => !conhecidos.has(chave(e)));

  const nomesAntigos = new Set(antes.subjects.map((s) => s.name));
  const disciplinas = depois.subjects
    .map((s) => s.name)
    .filter((nome) => !nomesAntigos.has(nome));

  return { eventos, disciplinas, frase: frasear(eventos, disciplinas) };
}

/**
 * A frase do aviso. Curta: ela aparece por cima da agenda, e quem está lendo
 * quer voltar para a agenda.
 *
 * "Novo em X" e não "novo prazo em X" porque a lista mistura entrega, prova e
 * webconferência — chamar webconferência de prazo foi um erro real deste
 * projeto, no texto da notificação.
 */
function frasear(eventos: AcademicEvent[], disciplinas: string[]): string | null {
  if (disciplinas.length === 1 && eventos.length === 0) {
    return `Nova disciplina na sua agenda: ${disciplinas[0]}`;
  }
  if (disciplinas.length > 1 && eventos.length === 0) {
    return `${disciplinas.length} disciplinas novas na sua agenda`;
  }
  if (eventos.length === 0) return null;

  if (eventos.length === 1) {
    const e = eventos[0];
    return `Novo em ${e.subject}: ${e.title}`;
  }

  const materias = new Set(eventos.map((e) => e.subject));
  if (materias.size === 1) {
    return `${eventos.length} novidades em ${eventos[0].subject}`;
  }
  return `${eventos.length} novidades na sua agenda`;
}
