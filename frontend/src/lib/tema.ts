/**
 * Tema claro e escuro.
 *
 * O padrão é seguir o sistema: quem já deixou o celular no escuro não deveria
 * precisar dizer isso de novo aqui. O botão da barra é uma exceção explícita —
 * e essa escolha, sim, fica guardada no navegador.
 *
 * `localStorage` guarda só a palavra "dark" ou "light". O token de sessão
 * continua fora dele, em memória, pelo motivo de sempre: XSS. Preferência de
 * cor não é segredo, e perdê-la a cada reload seria pior do que guardá-la.
 */

import { useCallback, useEffect, useState } from 'react';

export type Tema = 'light' | 'dark';

const CHAVE = 'agenda-tema';

/** O que o sistema operacional do aluno pede, quando ele não escolheu nada. */
export function temaDoSistema(): Tema {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** A escolha guardada, ou `null` quando o aluno nunca mexeu no botão. */
export function temaEscolhido(): Tema | null {
  const salvo = localStorage.getItem(CHAVE);
  return salvo === 'dark' || salvo === 'light' ? salvo : null;
}

/** O tema em vigor agora: a escolha do aluno, ou a do sistema. */
export function temaAtual(): Tema {
  return temaEscolhido() ?? temaDoSistema();
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

/**
 * O tema em vigor e o botão que o inverte.
 *
 * Enquanto o aluno não escolher nada, o app continua acompanhando o sistema em
 * tempo real: quem tem o celular no modo automático vê a tela virar sozinha ao
 * anoitecer, sem precisar recarregar. O primeiro clique no botão encerra esse
 * acompanhamento — a partir dali quem manda é a escolha dele.
 */
export function useTema(): { tema: Tema; alternar: () => void } {
  const [tema, setTema] = useState<Tema>(() => temaAtual());

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!mq) return;
    const aoMudar = () => {
      if (temaEscolhido()) return;
      const novo = temaDoSistema();
      document.documentElement.dataset.theme = novo;
      setTema(novo);
    };
    mq.addEventListener('change', aoMudar);
    return () => mq.removeEventListener('change', aoMudar);
  }, []);

  const alternar = useCallback(() => {
    setTema((atual) => {
      const novo: Tema = atual === 'dark' ? 'light' : 'dark';
      aplicarTema(novo);
      return novo;
    });
  }, []);

  return { tema, alternar };
}
