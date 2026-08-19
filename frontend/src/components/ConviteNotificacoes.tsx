import React from 'react';
import Icon from './Icon';
import { usePush } from '../lib/usePush';
import { adiarConvite, dispensarConvite, podeConvidar } from '../lib/avisoNotificacao';

interface ConviteNotificacoesProps {
  /** Matrícula do aluno — a preferência é por aluno e por aparelho. */
  username?: string;
}

/**
 * O convite para ligar as notificações, no topo da agenda.
 *
 * Fica insistente de propósito: volta a cada sessão enquanto o aluno não
 * decidir. O que impede isso de virar praga é a terceira opção — "Não mostre
 * isso novamente" resolve de vez, no aparelho, sem precisar entrar em
 * configuração nenhuma.
 *
 * Não aparece quando não há o que aceitar: sem chave no servidor, sem suporte
 * no navegador (iPhone fora da tela inicial), com a permissão já negada no
 * navegador ou com as notificações já ligadas.
 */
const ConviteNotificacoes: React.FC<ConviteNotificacoesProps> = ({ username = '' }) => {
  const { estado, ocupado, ligar } = usePush();
  // `decidido` guarda a resposta desta visita; o storage guarda as anteriores.
  // A consulta é refeita a cada render de propósito: a matrícula chega depois
  // do primeiro desenho (vem do /api/me), e ler só no mount usaria a chave
  // errada — a de "anônimo" — justo no aparelho compartilhado que a chave por
  // matrícula existe para proteger.
  const [decidido, setDecidido] = React.useState(false);
  const visivel = !decidido && Boolean(username) && podeConvidar(username);

  if (!visivel || estado !== 'desligado') return null;

  const responder = async (resposta: 'sim' | 'agora-nao' | 'nunca') => {
    if (resposta === 'sim') {
      await ligar();
      // Some tendo ligado ou não. Se o aluno recusou no diálogo do navegador,
      // perguntar de novo na mesma visita é insistência — na próxima sessão o
      // convite volta, que é o pedido: aparecer sempre até ele decidir.
      adiarConvite(username);
      setDecidido(true);
      return;
    }
    if (resposta === 'nunca') dispensarConvite(username);
    else adiarConvite(username);
    setDecidido(true);
  };

  return (
    <div className="convite" role="region" aria-label="Notificações">
      <span className="convite__icone" aria-hidden="true">
        <Icon name="alerta" size={1.05} />
      </span>

      <div className="convite__texto">
        <p className="convite__pergunta">Deseja receber notificações de compromissos?</p>
        <p className="convite__detalhe">
          Um resumo de manhã com o que vence hoje, e um aviso quando sair nota ou um prazo
          mudar de data.
        </p>
      </div>

      <div className="convite__acoes">
        <button
          type="button"
          className="btn-primary convite__sim"
          onClick={() => responder('sim')}
          disabled={ocupado}
        >
          {ocupado ? 'Ativando…' : 'Sim'}
        </button>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => responder('agora-nao')}
          disabled={ocupado}
        >
          Agora não
        </button>
        <button
          type="button"
          className="btn-ghost convite__nunca"
          onClick={() => responder('nunca')}
          disabled={ocupado}
        >
          Não mostre isso novamente
        </button>
      </div>
    </div>
  );
};

export default ConviteNotificacoes;
