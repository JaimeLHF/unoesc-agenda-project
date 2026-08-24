import React from 'react';
import Icon from './Icon';

interface AvisoNovidadesProps {
  /** A frase pronta (`compararAgendas`). `null` não desenha nada. */
  frase: string | null;
  onFechar: () => void;
}

/**
 * O que apareceu na agenda enquanto o aluno já estava olhando para ela.
 *
 * A agenda agora abre com o que estava salvo e busca o Moodle por baixo. Sem
 * este aviso, a lista mudaria sozinha na frente de quem está lendo — item
 * novo empurrando os outros para baixo, sem explicação. Ele fica no topo,
 * acima da lista, e não some sozinho: sumir por conta própria é apostar que o
 * aluno estava olhando naquele segundo.
 */
const AvisoNovidades: React.FC<AvisoNovidadesProps> = ({ frase, onFechar }) => {
  if (!frase) return null;

  return (
    <div className="aviso-novidades" role="status">
      <Icon name="sino" />
      <span className="aviso-novidades__texto">{frase}</span>
      <button
        type="button"
        className="aviso-novidades__fechar"
        onClick={onFechar}
        aria-label="Fechar aviso"
      >
        <Icon name="fechar" />
      </button>
    </div>
  );
};

export default AvisoNovidades;
