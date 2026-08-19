/**
 * Memória do convite de notificações: quem já disse "agora não" e quem disse
 * "não mostre mais".
 *
 * Fica no navegador, não no servidor: é preferência de *aparelho*, não de
 * conta. O aluno pode querer o aviso no celular e não no computador do
 * laboratório, e uma linha no banco por aparelho não diria isso.
 *
 * A chave inclui a matrícula pelo mesmo motivo do `lumiConversas`: no
 * laboratório o próximo aluno abre o mesmo Chrome, e ele não deve herdar o
 * "não mostre mais" de quem sentou antes.
 *
 * "Agora não" vai para o `sessionStorage` e morre quando a aba fecha — é a
 * resposta de quem não quis parar agora, não de quem não quer o recurso. "Não
 * mostre mais" vai para o `localStorage` e fica.
 */

const NUNCA = 'avisos:nunca';
const AGORA_NAO = 'avisos:agora-nao';

function chave(prefixo: string, username: string): string {
  return `${prefixo}:${username || 'anonimo'}`;
}

/* Navegador em modo restrito pode barrar o storage. Aí o convite volta a
   aparecer, que é melhor do que a tela quebrar. */
function ler(store: Storage, k: string): boolean {
  try {
    return store.getItem(k) === '1';
  } catch {
    return false;
  }
}

function gravar(store: Storage, k: string): void {
  try {
    store.setItem(k, '1');
  } catch {
    /* sem storage: o convite reaparece no próximo carregamento */
  }
}

/** O convite pode ser mostrado para este aluno, neste aparelho? */
export function podeConvidar(username: string): boolean {
  return (
    !ler(localStorage, chave(NUNCA, username)) &&
    !ler(sessionStorage, chave(AGORA_NAO, username))
  );
}

/** "Agora não" — some até a aba fechar. */
export function adiarConvite(username: string): void {
  gravar(sessionStorage, chave(AGORA_NAO, username));
}

/** "Não mostre isso novamente" — some para sempre neste aparelho. */
export function dispensarConvite(username: string): void {
  gravar(localStorage, chave(NUNCA, username));
}

/**
 * Devolve o convite para quem mudou de ideia. Chamado quando o aluno liga as
 * notificações pelo perfil e depois desliga — sem isto, quem apertou "não
 * mostre mais" uma vez ficaria sem caminho de volta a não ser limpar o
 * navegador.
 */
export function reativarConvite(username: string): void {
  try {
    localStorage.removeItem(chave(NUNCA, username));
    sessionStorage.removeItem(chave(AGORA_NAO, username));
  } catch {
    /* sem storage: nada a limpar */
  }
}
