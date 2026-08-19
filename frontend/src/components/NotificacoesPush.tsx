import React from 'react';
import Icon from './Icon';
import { usePush } from '../lib/usePush';
import { reativarConvite } from '../lib/avisoNotificacao';

interface NotificacoesPushProps {
  /** Matrícula — usada para devolver o convite a quem desligar os avisos. */
  username?: string;
}

/**
 * Ligar e desligar as notificações na tela bloqueada.
 *
 * O estado mora no `usePush`, compartilhado com o convite que aparece na
 * agenda: com a lógica duplicada, ligar num lugar deixava o outro dizendo
 * "desligado" até o próximo reload.
 *
 * O texto sobre a senha não é rodapé jurídico — é a informação que muda a
 * decisão. Para avisar "saiu nota" com o app fechado, o servidor consulta o
 * Moodle sozinho, e isso significa guardar a senha cifrada enquanto as
 * notificações estiverem ligadas.
 */
const NotificacoesPush: React.FC<NotificacoesPushProps> = ({ username = '' }) => {
  const { config, estado, ocupado, recado, ligar, desligar, testar } = usePush();

  const desligarEReabrirConvite = async () => {
    await desligar();
    // Quem desliga aqui pode ter apertado "não mostre mais" antes. Sem
    // devolver o convite, o caminho de volta seria limpar o navegador.
    reativarConvite(username);
  };

  if (estado === 'carregando') return null;

  if (estado === 'indisponivel') {
    // Sem chave no servidor não há o que dizer ao aluno — o recurso não
    // existe. Sem suporte no navegador, existe e o caminho é instalar o app.
    if (!config?.enabled) return null;
    return (
      <div className="push">
        <h3 className="push__titulo">
          <Icon name="alerta" size={1} />
          Avisos no celular
        </h3>
        <p className="push__texto">
          Este navegador não recebe notificações. No iPhone elas só funcionam com o app
          instalado na tela inicial — veja “Instalar no celular”, logo abaixo.
        </p>
      </div>
    );
  }

  return (
    <div className="push">
      <h3 className="push__titulo">
        <Icon name="alerta" size={1} />
        Avisos no celular
      </h3>

      <p className="push__texto">
        Um resumo às 7h com o que vence hoje, um aviso às 19h do que vence amanhã, e na
        hora quando sair nota ou um prazo mudar de data.
      </p>

      {/*
        Isto não é aviso legal de rodapé: é a informação que muda a decisão. Sem
        ela, o aluno liga notificação sem saber que autorizou o servidor a
        entrar no Moodle por ele três vezes por dia.
      */}
      <p className="push__aviso">
        Para avisar com o app fechado, o servidor consulta o Moodle por você três vezes
        ao dia — e para isso guarda sua senha cifrada enquanto os avisos estiverem
        ligados. Ao desligar, ela é apagada na hora.
      </p>

      {estado === 'negado' ? (
        <p className="push__texto push__texto--erro">
          Você bloqueou as notificações deste site. O navegador não pergunta de novo:
          libere em Configurações do site → Notificações e volte aqui.
        </p>
      ) : (
        <div className="push__acoes">
          {estado === 'ligado' ? (
            <>
              <button type="button" className="btn-secondary" onClick={testar} disabled={ocupado}>
                Enviar teste
              </button>
              <button type="button" className="btn-ghost" onClick={desligarEReabrirConvite} disabled={ocupado}>
                Desligar avisos
              </button>
            </>
          ) : (
            <button type="button" className="btn-primary" onClick={ligar} disabled={ocupado}>
              {ocupado ? 'Ativando…' : 'Ativar avisos neste aparelho'}
            </button>
          )}
        </div>
      )}

      {recado && <p className="push__recado">{recado}</p>}

      {config && config.devices > 1 && (
        <p className="push__texto">
          Esta conta recebe avisos em {config.devices} aparelhos.
        </p>
      )}
    </div>
  );
};

export default NotificacoesPush;
