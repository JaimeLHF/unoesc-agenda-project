/**
 * O cartão da semana: uma imagem para mandar no grupo da turma.
 *
 * Existe por um motivo prático — este app cresce por indicação de colega, e um
 * link solto no grupo não diz o que ele faz. Uma imagem com os prazos da
 * semana diz, e chega junto com a resposta que alguém pediu ("o que tem essa
 * semana?").
 *
 * Desenhado em `<canvas>` na mão, sem biblioteca: são oito linhas de texto num
 * retângulo, e qualquer pacote de captura de tela custaria mais que o app
 * inteiro pesa hoje. O compartilhamento tenta primeiro o `navigator.share` com
 * arquivo, que é o caminho do celular (abre o WhatsApp direto); onde ele não
 * existe, cai no download do PNG.
 *
 * O que a imagem **não** leva: nome do aluno, matrícula e nota. Ela vai para um
 * grupo — o que aparece ali é o que qualquer colega da turma já sabe.
 */
import type { AcademicEvent } from '../types';

const LARGURA = 1080;
const MARGEM = 80;
// Altura conforme o que a semana tem: com três compromissos, a moldura fixa de
// 1350px deixava metade do cartão vazio e ele parecia um erro de renderização.
const ALTURA_MINIMA = 900;
const ALTURA_POR_EVENTO = 118;

const TIPO: Record<string, string> = {
  webconference: 'Webconferência',
  exam: 'Prova',
  deadline: 'Entrega',
  other: 'Evento',
};

function diaEMes(iso: string): string {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}` : iso;
}

function semCodigo(nome: string): string {
  const partes = nome.split(' - ');
  return partes.length > 1 && /^\d+$/.test(partes[0].trim()) ? partes.slice(1).join(' - ') : nome;
}

/** Desenha o cartão e devolve o PNG. */
export async function desenharCartao(
  eventos: AcademicEvent[],
  intervalo: string,
): Promise<Blob | null> {
  const visiveis = Math.min(eventos.length, 8);
  const altura = Math.max(ALTURA_MINIMA, 560 + visiveis * ALTURA_POR_EVENTO);

  const canvas = document.createElement('canvas');
  canvas.width = LARGURA;
  canvas.height = altura;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  ctx.fillStyle = '#0f172a';
  ctx.fillRect(0, 0, LARGURA, altura);

  ctx.fillStyle = '#60a5fa';
  ctx.font = 'bold 34px system-ui, -apple-system, Segoe UI, sans-serif';
  ctx.fillText('AGENDA UNOESC', MARGEM, 130);

  ctx.fillStyle = '#f8fafc';
  ctx.font = 'bold 72px system-ui, -apple-system, Segoe UI, sans-serif';
  ctx.fillText('Minha semana', MARGEM, 225);

  ctx.fillStyle = '#94a3b8';
  ctx.font = '36px system-ui, -apple-system, Segoe UI, sans-serif';
  ctx.fillText(intervalo, MARGEM, 285);

  let y = 400;

  if (eventos.length === 0) {
    ctx.fillStyle = '#cbd5e1';
    ctx.font = '40px system-ui, -apple-system, Segoe UI, sans-serif';
    ctx.fillText('Nada marcado nesta semana.', MARGEM, y);
  }

  // Oito é o que cabe sem apertar; o resto vira uma linha de contagem, que é
  // mais honesto do que cortar no meio e deixar parecer que a semana acabou.
  for (const evento of eventos.slice(0, 8)) {
    ctx.fillStyle = '#60a5fa';
    ctx.font = 'bold 40px system-ui, -apple-system, Segoe UI, sans-serif';
    ctx.fillText(diaEMes(evento.date), MARGEM, y);

    ctx.fillStyle = '#f8fafc';
    ctx.font = 'bold 40px system-ui, -apple-system, Segoe UI, sans-serif';
    const titulo = evento.title.length > 34 ? `${evento.title.slice(0, 33)}…` : evento.title;
    ctx.fillText(titulo, MARGEM + 160, y);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '32px system-ui, -apple-system, Segoe UI, sans-serif';
    const linha = `${TIPO[evento.type] ?? 'Evento'} · ${semCodigo(evento.subject)}${
      evento.time ? ` · ${evento.time}` : ''
    }`;
    ctx.fillText(linha.length > 52 ? `${linha.slice(0, 51)}…` : linha, MARGEM + 160, y + 46);

    y += 118;
  }

  if (eventos.length > 8) {
    ctx.fillStyle = '#94a3b8';
    ctx.font = '34px system-ui, -apple-system, Segoe UI, sans-serif';
    ctx.fillText(`e mais ${eventos.length - 8} compromisso(s)`, MARGEM, y);
  }

  ctx.fillStyle = '#64748b';
  ctx.font = '30px system-ui, -apple-system, Segoe UI, sans-serif';
  ctx.fillText('unoesc-agenda.fly.dev', MARGEM, altura - 120);
  ctx.fillText('Projeto de alunos — não é serviço oficial da UNOESC.', MARGEM, altura - 72);

  return new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
}

/**
 * Compartilha o cartão. Devolve `false` quando não deu para fazer nada — aí a
 * tela precisa dizer isso, em vez de fingir que compartilhou.
 */
export async function compartilharCartao(
  eventos: AcademicEvent[],
  intervalo: string,
): Promise<boolean> {
  const png = await desenharCartao(eventos, intervalo);
  if (!png) return false;

  const arquivo = new File([png], 'minha-semana.png', { type: 'image/png' });

  // O caminho do celular: abre a folha de compartilhamento do sistema, com o
  // WhatsApp na primeira posição. `canShare` com arquivo é o único jeito
  // confiável de saber se o navegador aceita — o `share` existe em lugares
  // onde arquivo não passa.
  if (navigator.canShare?.({ files: [arquivo] })) {
    try {
      await navigator.share({ files: [arquivo], title: 'Minha semana' });
      return true;
    } catch (err) {
      // Cancelar não é falha: quem fechou a folha de compartilhamento não
      // quer ver mensagem de erro por isso.
      return (err as Error)?.name === 'AbortError';
    }
  }

  const url = URL.createObjectURL(png);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'minha-semana.png';
  link.click();
  URL.revokeObjectURL(url);
  return true;
}
