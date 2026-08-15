import React from 'react';
import Icon from './Icon';
import { useTema } from '../lib/tema';

interface ThemeToggleProps {
  /** Classe extra para posicionar o botão no contexto de cada tela. */
  className?: string;
}

/**
 * Claro ou escuro, num botão só.
 *
 * O ícone mostra para onde a tela vai, não onde ela está: com dois estados, um
 * sol na tela escura é a promessa do clique, e é assim que todo mundo já está
 * acostumado a ler esse botão.
 *
 * Aparece na barra do app e também na tela de entrada, que não tem barra — quem
 * abre o app à noite não deveria precisar fazer login antes de poder baixar o
 * brilho da tela.
 */
const ThemeToggle: React.FC<ThemeToggleProps> = ({ className }) => {
  const { tema, alternar } = useTema();
  const rotulo = tema === 'dark' ? 'Usar o tema claro' : 'Usar o tema escuro';

  return (
    <button
      type="button"
      className={className ? `btn-icon ${className}` : 'btn-icon'}
      onClick={alternar}
      title={rotulo}
    >
      <Icon name={tema === 'dark' ? 'sol' : 'lua'} label={rotulo} />
    </button>
  );
};

export default ThemeToggle;
