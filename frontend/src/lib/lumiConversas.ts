/**
 * Conversas com a Lumi, guardadas no navegador.
 *
 * Ficam no `localStorage` e não no servidor de propósito: o backend teria de
 * ganhar tabela, endpoint e entrada no teste de isolamento para guardar algo
 * que só interessa a quem escreveu. Se um dia o aluno quiser a conversa no
 * celular *e* no notebook, aí vale o custo.
 *
 * A chave inclui a matrícula porque a máquina pode ser compartilhada — no
 * laboratório da UNOESC o próximo aluno usa o mesmo Chrome, e uma conversa
 * que lista as atividades de outra pessoa é vazamento, mesmo sem senha junto.
 */

export interface LumiMensagem {
  role: 'user' | 'assistant';
  content: string;
}

export interface LumiConversa {
  id: string;
  /** Primeira pergunta, cortada — é como a pessoa reconhece a conversa. */
  titulo: string;
  criadaEm: number;
  mensagens: LumiMensagem[];
}

/** Quantas conversas ficam guardadas. Além disso vira arquivo morto. */
const MAX_CONVERSAS = 20;

function chave(username: string): string {
  return `lumi:conversas:${username}`;
}

export function carregar(username: string): LumiConversa[] {
  try {
    const bruto = localStorage.getItem(chave(username));
    if (!bruto) return [];
    const dados = JSON.parse(bruto) as LumiConversa[];
    return Array.isArray(dados) ? dados : [];
  } catch {
    // Storage cheio, desativado (navegação anônima) ou JSON de uma versão
    // antiga: a conversa é conveniência, não pode derrubar a tela.
    return [];
  }
}

export function salvar(username: string, conversas: LumiConversa[]): void {
  try {
    localStorage.setItem(chave(username), JSON.stringify(conversas.slice(0, MAX_CONVERSAS)));
  } catch {
    /* idem: falhar em silêncio é melhor que perder a resposta na tela */
  }
}

export function apagarTudo(username: string): void {
  try {
    localStorage.removeItem(chave(username));
  } catch {
    /* idem */
  }
}

/** Título a partir da primeira pergunta — sem cortar palavra no meio. */
export function tituloDaPergunta(pergunta: string): string {
  const limpo = pergunta.trim().replace(/\s+/g, ' ');
  if (limpo.length <= 42) return limpo;
  const corte = limpo.slice(0, 42);
  const espaco = corte.lastIndexOf(' ');
  return `${(espaco > 20 ? corte.slice(0, espaco) : corte).trim()}…`;
}

/** Id sem dependência: o `crypto.randomUUID` não existe em http:// no Android. */
export function novoId(): string {
  return `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}
