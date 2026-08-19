import React from 'react';
import Icon from './Icon';
import {
  fetchPushConfig,
  subscribePush,
  testPush,
  unsubscribePush,
  type PushConfig,
} from '../services/api';

/**
 * Ligar e desligar as notificações na tela bloqueada.
 *
 * Três coisas precisam ser verdade para o botão funcionar, e cada uma falha de
 * um jeito diferente:
 *
 * 1. O servidor tem chave VAPID (`config.enabled`) — se não, o bloco some
 *    inteiro, como a Lumi sem chave de IA.
 * 2. O navegador tem Push API. No iPhone ela **só existe com o app instalado
 *    na tela inicial** — no Safari comum nem aparece, e por isso a mensagem
 *    aponta para lá em vez de mostrar um botão que não faz nada.
 * 3. O aluno autoriza. Negado é definitivo: o navegador não pergunta duas
 *    vezes, e a tela precisa dizer que a volta é pelas configurações do site.
 *
 * O texto sobre a senha não é rodapé jurídico — é a informação que muda a
 * decisão. Para avisar "saiu nota" com o app fechado, o servidor consulta o
 * Moodle sozinho, e isso significa guardar a senha cifrada enquanto as
 * notificações estiverem ligadas.
 */

/**
 * A chave pública vem em base64url; a Push API quer bytes.
 *
 * O tipo de retorno é `ArrayBuffer` e não `Uint8Array` porque o TypeScript
 * moderno parametriza o array pelo tipo do buffer, e `applicationServerKey`
 * não aceita um que possa ser `SharedArrayBuffer`. O `.buffer` resolve sem
 * `as any`.
 */
function chaveParaBytes(base64url: string): ArrayBuffer {
  const preenchido = base64url.padEnd(base64url.length + ((4 - (base64url.length % 4)) % 4), '=');
  const bruto = atob(preenchido.replace(/-/g, '+').replace(/_/g, '/'));
  const bytes = new Uint8Array(bruto.length);
  for (let i = 0; i < bruto.length; i += 1) bytes[i] = bruto.charCodeAt(i);
  return bytes.buffer;
}

type Estado = 'carregando' | 'indisponivel' | 'desligado' | 'ligado' | 'negado';

const NotificacoesPush: React.FC = () => {
  const [config, setConfig] = React.useState<PushConfig | null>(null);
  const [estado, setEstado] = React.useState<Estado>('carregando');
  const [ocupado, setOcupado] = React.useState(false);
  const [recado, setRecado] = React.useState<string | null>(null);

  const suportado =
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window;

  React.useEffect(() => {
    let ativo = true;

    fetchPushConfig()
      .then(async (c) => {
        if (!ativo) return;
        setConfig(c);

        if (!c.enabled || !suportado) {
          setEstado('indisponivel');
          return;
        }
        if (Notification.permission === 'denied') {
          setEstado('negado');
          return;
        }

        // A conta pode ter outro aparelho inscrito; o que decide o botão
        // desta tela é a inscrição *deste* navegador.
        const registro = await navigator.serviceWorker.getRegistration();
        const inscricao = await registro?.pushManager.getSubscription();
        setEstado(inscricao ? 'ligado' : 'desligado');
      })
      .catch(() => ativo && setEstado('indisponivel'));

    return () => {
      ativo = false;
    };
  }, [suportado]);

  const ligar = async () => {
    if (!config?.public_key) return;
    setOcupado(true);
    setRecado(null);
    try {
      const permissao = await Notification.requestPermission();
      if (permissao !== 'granted') {
        setEstado(permissao === 'denied' ? 'negado' : 'desligado');
        return;
      }

      const registro = await navigator.serviceWorker.ready;
      const inscricao = await registro.pushManager.subscribe({
        // O Chrome exige `true`: não existe push silencioso na web, toda
        // mensagem tem de virar notificação visível.
        userVisibleOnly: true,
        applicationServerKey: chaveParaBytes(config.public_key),
      });

      setConfig(await subscribePush(inscricao.toJSON() as PushSubscriptionJSON));
      setEstado('ligado');
      setRecado('Pronto. Mande um teste para conferir.');
    } catch {
      setRecado('Não consegui ativar agora. Tente de novo em instantes.');
    } finally {
      setOcupado(false);
    }
  };

  const desligar = async () => {
    setOcupado(true);
    setRecado(null);
    try {
      const registro = await navigator.serviceWorker.getRegistration();
      const inscricao = await registro?.pushManager.getSubscription();
      if (inscricao) {
        await inscricao.unsubscribe();
        setConfig(await unsubscribePush(inscricao.endpoint));
      } else {
        setConfig(await unsubscribePush());
      }
      setEstado('desligado');
      setRecado('Notificações desligadas. Sua senha guardada foi apagada.');
    } catch {
      setRecado('Não consegui desligar agora. Tente de novo.');
    } finally {
      setOcupado(false);
    }
  };

  const testar = async () => {
    setOcupado(true);
    setRecado(null);
    try {
      await testPush();
      setRecado('Enviei. Deve chegar em alguns segundos.');
    } catch {
      setRecado('Não consegui entregar. Confira se as notificações estão liberadas.');
    } finally {
      setOcupado(false);
    }
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
              <button type="button" className="btn-ghost" onClick={desligar} disabled={ocupado}>
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
