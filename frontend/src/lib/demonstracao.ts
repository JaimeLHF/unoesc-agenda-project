/**
 * A agenda de mentira que a tela de entrada mostra a quem ainda não entrou.
 *
 * Quem chega aqui pela primeira vez tem de digitar a matrícula e a senha do
 * Moodle antes de ver qualquer coisa — é muita confiança pedida a um app que
 * ele nunca viu funcionando. Esta é a resposta: a mesma agenda, com os mesmos
 * componentes, montada com dados inventados.
 *
 * Duas regras que fazem a demonstração continuar honesta:
 *
 * 1. **As datas são relativas a hoje.** Datas fixas envelhecem e a demo
 *    abriria com uma semana vazia e tudo "Há 30 dias" — que é exatamente a
 *    tela que não convence ninguém.
 * 2. **Nada aqui imita uma pessoa real.** Nomes de disciplina são os da grade,
 *    e não há aluno, professor nem nota de ninguém.
 *
 * Os selos existem de propósito: prazo adiado, nota que saiu, data lida do
 * PDF, material novo na sala e semana cheia são o que o app faz de diferente
 * de olhar o Moodle — e nenhum deles aparece numa captura de tela parada.
 */
import type { AcademicEvent, Subject } from '../types';

const DIA_MS = 24 * 60 * 60 * 1000;

/** "2026-09-04" para daqui a N dias, no fuso de quem está olhando. */
function emDias(dias: number): string {
  const d = new Date(Date.now() + dias * DIA_MS);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`;
}

/** Epoch em segundos, que é como o Moodle manda início e fim do componente. */
function epochEmDias(dias: number): number {
  return Math.round((Date.now() + dias * DIA_MS) / 1000);
}

export interface AgendaDeExemplo {
  subjects: Subject[];
  events: AcademicEvent[];
  lastScrapedAt: string;
}

/**
 * A agenda de exemplo, recalculada a cada chamada para que "falta 1 dia"
 * continue sendo verdade amanhã.
 */
export function agendaDeExemplo(): AgendaDeExemplo {
  const semestre = { start_date: epochEmDias(-40), end_date: epochEmDias(80) };

  const subjects: Subject[] = [
    {
      id: 'demo-empreendedorismo',
      name: '24728 - EMPREENDEDORISMO E INOVAÇÃO',
      ...semestre,
    },
    {
      id: 'demo-banco',
      name: '31002 - BANCO DE DADOS',
      ...semestre,
    },
    {
      id: 'demo-mobile',
      name: '28743 - DESENVOLVIMENTO MOBILE',
      ...semestre,
      // Nota que acabou de sair: é o aviso que a UNOESC manda por e-mail e o
      // aluno só vê quando abre o Moodle.
      final_grade: 90,
      grade_changed: true,
      previous_grade: null,
    },
    {
      id: 'demo-engenharia',
      name: '10275 - ENGENHARIA DE SOFTWARE',
      ...semestre,
      new_materials: [
        { name: 'Slides da aula 9', modname: 'resource' },
        { name: 'Gabarito da lista 3', modname: 'resource' },
      ],
      pending_activities: [{ name: 'Trabalho final (sem data no Moodle)', modname: 'assign' }],
    },
  ];

  const events: AcademicEvent[] = [
    {
      id: 'demo-webconf',
      stable_key: 'demo-webconf',
      title: 'Webconferência 1',
      date: emDias(1),
      time: '19:00',
      description: 'Encontro ao vivo da Unidade 1.',
      subject: '24728 - EMPREENDEDORISMO E INOVAÇÃO',
      type: 'webconference',
      source: 'moodle_course_text',
    },
    {
      id: 'demo-av2',
      stable_key: 'demo-av2',
      title: 'Avaliação 2',
      date: emDias(3),
      time: '23:59',
      description: 'Modelagem relacional — envio pelo Moodle.',
      subject: '31002 - BANCO DE DADOS',
      type: 'exam',
      source: 'moodle_calendar',
      // O professor empurrou a data e a agenda diz de onde ela veio.
      previous_date: emDias(1),
    },
    {
      id: 'demo-av1-mobile',
      stable_key: 'demo-av1-mobile',
      title: 'Atividade Avaliativa 1',
      date: emDias(5),
      time: '23:59',
      description: 'Entrega do protótipo navegável.',
      subject: '28743 - DESENVOLVIMENTO MOBILE',
      type: 'deadline',
      // Data que estava dentro do PDF da disciplina, não no calendário: a tela
      // marca com o selo "PDF" porque regex não vale o mesmo que cadastro.
      source: 'pdf_curso',
      weight: 4,
    },
    {
      id: 'demo-forum',
      stable_key: 'demo-forum',
      title: 'Fórum de discussão — Unidade 2',
      date: emDias(6),
      time: '23:59',
      description: 'Participação vale nota.',
      subject: '10275 - ENGENHARIA DE SOFTWARE',
      type: 'deadline',
      source: 'moodle_calendar',
    },
    {
      id: 'demo-prova',
      stable_key: 'demo-prova',
      title: 'Prova da Unidade 1',
      date: emDias(12),
      time: '19:00',
      description: 'Presencial, no polo.',
      subject: '31002 - BANCO DE DADOS',
      type: 'exam',
      source: 'moodle_calendar',
    },
  ];

  return { subjects, events, lastScrapedAt: new Date().toISOString() };
}
