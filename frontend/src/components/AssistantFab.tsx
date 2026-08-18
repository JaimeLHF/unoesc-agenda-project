import React from 'react';
import Icon from './Icon';

interface AssistantFabProps {
  onClick: () => void;
  /** Perguntas que ainda cabem no mês. Zero não esconde o botão: a tela do
      Lumi explica a cota melhor do que um botão que some sem dizer por quê. */
  restantes: number;
}

/**
 * Botão flutuante da Lumi, no canto inferior direito.
 *
 * Ficava só na barra de cima, junto de Atualizar e do menu da conta — onde o
 * aluno passa uma vez, ao abrir o app, e não volta mais. A dúvida que Lumi
 * responde ("por onde eu começo?") nasce olhando a agenda, e é ali que o botão
 * precisa estar.
 *
 * No celular vira só o círculo com o ícone: o rótulo comeria a largura da
 * lista de eventos que está atrás.
 */
const AssistantFab: React.FC<AssistantFabProps> = ({ onClick, restantes }) => (
  <button
    type="button"
    className="fab-lumi"
    onClick={onClick}
    title={
      restantes > 0
        ? `Falar com Lumi sobre seus prazos (${restantes} perguntas neste mês)`
        : 'Você usou todas as perguntas deste mês'
    }
    aria-label="Falar com Lumi"
  >
    <Icon name="organizar" size={1.15} />
    <span className="fab-lumi__label">Lumi</span>
  </button>
);

export default AssistantFab;
