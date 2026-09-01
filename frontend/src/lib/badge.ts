/**
 * O número no ícone do app, na tela inicial do celular.
 *
 * É a única forma de o app dizer alguma coisa sem gastar uma notificação: o
 * aluno vê "2" no ícone ao desbloquear o telefone e sabe que tem compromisso
 * hoje, sem nenhum aviso ter tocado. Vale principalmente para quem recusou a
 * notificação — e no iPhone é o mesmo canal, então quem já autorizou os avisos
 * também tem o número.
 *
 * A API é `navigator.setAppBadge`, que só existe no app instalado na tela
 * inicial (iOS 16.4+, Android/Chrome). Fora disso o método não está lá, e
 * chamar direto quebraria a tela inteira — daí todo o cuidado abaixo: sem
 * suporte, esta função simplesmente não faz nada, e nenhuma parte do app
 * depende dela ter funcionado.
 */

export function atualizarBadge(quantidade: number): void {
  // O TypeScript já declara os dois métodos, mas o navegador do aluno pode não
  // tê-los: a checagem é de execução, não de tipo.
  const nav = navigator as Partial<Navigator>;

  try {
    if (quantidade > 0) {
      void nav.setAppBadge?.(quantidade)?.catch(() => {});
    } else {
      void nav.clearAppBadge?.()?.catch(() => {});
    }
  } catch {
    // Navegador sem suporte, ou permissão recusada. O ícone fica limpo, que é
    // exatamente o que ele já era.
  }
}
