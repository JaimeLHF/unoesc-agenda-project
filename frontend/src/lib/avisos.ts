/**
 * Os dois avisos que a agenda dá sobre um evento: que a data mudou e quanto a
 * avaliação vale.
 *
 * Ficam aqui, e não dentro de uma tela, porque o mesmo evento aparece na
 * semana, no cartão da disciplina e na página da atividade — e um selo que diz
 * "Adiado" numa tela e nada em outra é pior que não ter selo nenhum.
 */
import type { AcademicEvent } from '../types';

export interface MudancaDePrazo {
  /** "Adiado" quando a data foi empurrada para frente. */
  rotulo: 'Adiado' | 'Antecipado';
  /** A data antiga, já formatada em DD/MM. */
  de: string;
}

/** "2026-09-10" → "10/09". Devolve o texto cru se não for uma data ISO. */
function diaEMes(iso: string): string {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}` : iso;
}

/**
 * O evento mudou de data desde a última vez que o app olhou?
 *
 * O backend só manda `previous_date` enquanto a mudança é recente — passado o
 * prazo do aviso, o campo vem vazio e o selo some sozinho.
 */
export function mudancaDePrazo(evento: AcademicEvent): MudancaDePrazo | null {
  const antes = evento.previous_date;
  if (!antes || antes === evento.date) return null;
  return {
    rotulo: antes < evento.date ? 'Adiado' : 'Antecipado',
    de: diaEMes(antes),
  };
}

/**
 * "Peso 4" / "Peso 0,2". Só existe em prazo lido do PDF: o calendário do
 * Moodle não carrega quanto a avaliação vale.
 */
export function formatarPeso(peso?: number | null): string | null {
  if (typeof peso !== 'number' || !isFinite(peso) || peso <= 0) return null;
  return `Peso ${peso.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}`;
}
