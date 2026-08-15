/**
 * O nome do aluno em pedaços — a barra e o perfil mostram o mesmo nome em
 * tamanhos diferentes, e as duas telas precisam cortá-lo do mesmo jeito.
 */

/**
 * Iniciais para o avatar: primeira e última do nome. "Jaime Luiz Hansen Filho"
 * vira "JF" — o suficiente para o aluno reconhecer a própria conta na barra.
 */
export function iniciais(nome: string, alternativa: string): string {
  const partes = nome.trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return alternativa.slice(0, 2).toUpperCase();
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

/**
 * Só o primeiro nome, para a barra. O nome completo de um aluno tem quatro
 * palavras e empurraria a marca para fora da tela; a matrícula, que ficava
 * aqui antes, ninguém reconhece de relance.
 */
export function primeiroNome(nome: string): string {
  return nome.trim().split(/\s+/)[0] ?? '';
}
