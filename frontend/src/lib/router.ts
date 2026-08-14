import { useEffect, useState } from 'react';

/**
 * Roteador mínimo, sem dependência.
 *
 * O app tem duas rotas: a agenda (`/`) e a atividade (`/atividade/<chave>`).
 * Trazer o react-router para isso custaria mais bytes no 4G do que o app
 * inteiro ganha — e a única coisa que precisamos é do endereço mudar junto
 * com a tela, para o botão voltar do navegador funcionar e o link poder ser
 * compartilhado.
 */

const PREFIXO = '/atividade/';

/** Empurra um endereço novo e avisa quem estiver ouvindo. */
export function navigate(path: string): void {
  if (path === window.location.pathname) return;
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

/** Endereço da página de uma atividade. */
export function activityPath(stableKey: string): string {
  return `${PREFIXO}${encodeURIComponent(stableKey)}`;
}

/**
 * A chave da atividade no endereço atual, ou `null` quando estamos na agenda.
 * Reage ao botão voltar do navegador e às chamadas de `navigate`.
 */
export function useActivityRoute(): string | null {
  const [key, setKey] = useState(() => parse(window.location.pathname));

  useEffect(() => {
    const onChange = () => setKey(parse(window.location.pathname));
    window.addEventListener('popstate', onChange);
    return () => window.removeEventListener('popstate', onChange);
  }, []);

  return key;
}

function parse(pathname: string): string | null {
  if (!pathname.startsWith(PREFIXO)) return null;
  const bruto = pathname.slice(PREFIXO.length);
  if (!bruto) return null;
  try {
    return decodeURIComponent(bruto);
  } catch {
    return bruto;
  }
}
