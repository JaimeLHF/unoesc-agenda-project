import React from 'react';
import Icon from './Icon';

interface AssistantFabProps {
  onClick: () => void;
  /** Perguntas que ainda cabem no mês. Zero não esconde o botão: a tela da
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
 * Diz o que faz, e não só o nome: "Lumi" sozinho é uma palavra que o aluno
 * nunca viu. No celular fica o círculo com o brilho de IA — o rótulo comeria a
 * largura da lista que está atrás.
 */
const AssistantFab: React.FC<AssistantFabProps> = ({ onClick, restantes }) => (
  <button
    type="button"
    className="fab-lumi"
    onClick={onClick}
    title={
      restantes > 0
        ? `Perguntar à Lumi sobre seus prazos (${restantes} perguntas neste mês)`
        : 'Você usou todas as perguntas deste mês'
    }
    aria-label="Perguntar à Lumi sobre seus prazos"
  >
    <span className="fab-lumi__icone" aria-hidden="true">
      <Icon name="ia" size={1.4} />
    </span>
    <span className="fab-lumi__texto">
      <span className="fab-lumi__nome">Perguntar à Lumi</span>
      <span className="fab-lumi__sub">
        {restantes > 0 ? 'Organize seus prazos com IA' : 'Sem perguntas neste mês'}
      </span>
    </span>
  </button>
);

export default AssistantFab;
