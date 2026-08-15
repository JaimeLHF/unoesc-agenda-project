/**
 * Tema claro e escuro.
 *
 * O claro é o padrão, mesmo para quem usa o celular no escuro: é a cara do app
 * e é como ele aparece na primeira visita. O escuro existe para quem pedir, no
 * botão da barra — e essa escolha, sim, fica guardada no navegador.
 *
 * `localStorage` guarda só a palavra "dark" ou "light". O token de sessão
 * continua fora dele, em memória, pelo motivo de sempre: XSS. Preferência de
 * cor não é segredo, e perdê-la a cada reload seria pior do que guardá-la.
 */

import { useCallback, useState } from 'react';

export type Tema = 'light' | 'dark';

const CHAVE = 'agenda-tema';

/** A escolha guardada, ou `null` quando o aluno nunca mexeu no botão. */
export function temaEscolhido(): Tema | null {
  const salvo = localStorage.getItem(CHAVE);
  return salvo === 'dark' || salvo === 'light' ? salvo : null;
}

/** O tema em vigor agora: a escolha do aluno, ou o claro. */
export function temaAtual(): Tema {
  return temaEscolhido() ?? 'light';
}

/**
 * Aplica o tema no `<html>` e guarda a escolha.
 *
 * O atributo é o mesmo que o script do `index.html` escreve antes do React
 * montar — sem ele a tela pisca branca por um instante antes de escurecer.
 */
export function aplicarTema(tema: Tema): void {
  document.documentElement.dataset.theme = tema;
  localStorage.setItem(CHAVE, tema);
  // A barra de endereço do navegador no celular acompanha a tela.
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', tema === 'dark' ? '#0f172a' : '#ffffff');
}

/** O tema em vigor e o botão que o inverte. */
export function useTema(): { tema: Tema; alternar: () => void } {
  const [tema, setTema] = useState<Tema>(() => temaAtual());

  const alternar = useCallback(() => {
    setTema((atual) => {
      const novo: Tema = atual === 'dark' ? 'light' : 'dark';
      aplicarTema(novo);
      return novo;
    });
  }, []);

  return { tema, alternar };
}
