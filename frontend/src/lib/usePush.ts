/**
 * Estado das notificações push, num lugar só.
 *
 * Duas telas perguntam a mesma coisa — o alerta na agenda e o bloco do perfil.
 * Com a lógica duplicada, uma ligava e a outra continuava dizendo "desligado"
 * até o próximo reload.
 *
 * Três coisas precisam ser verdade para o aluno poder ativar, e cada uma falha
 * de um jeito diferente:
 *
 * 1. O servidor tem chave VAPID (`config.enabled`).
 * 2. O navegador tem Push API. No iPhone ela **só existe com o app instalado
 *    na tela inicial** — no Safari comum nem aparece.
 * 3. O aluno autoriza. Negado é definitivo: o navegador não pergunta duas
 *    vezes, e a volta é pelas configurações do site.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  fetchPushConfig,
  subscribePush,
  testPush,
  unsubscribePush,
  type PushConfig,
} from '../services/api';

export type EstadoPush =
  | 'carregando'
  | 'indisponivel' // sem chave no servidor ou sem suporte no navegador
  | 'desligado'
  | 'ligado'
  | 'negado';

/** A chave pública vem em base64url; a Push API quer bytes. */
function chaveParaBytes(base64url: string): ArrayBuffer {
  const preenchido = base64url.padEnd(base64url.length + ((4 - (base64url.length % 4)) % 4), '=');
  const bruto = atob(preenchido.replace(/-/g, '+').replace(/_/g, '/'));
  const bytes = new Uint8Array(bruto.length);
  for (let i = 0; i < bruto.length; i += 1) bytes[i] = bruto.charCodeAt(i);
  return bytes.buffer;
}

export const suportaPush =
  typeof window !== 'undefined' &&
  'serviceWorker' in navigator &&
  'PushManager' in window &&
  'Notification' in window;

export function usePush() {
  const [config, setConfig] = useState<PushConfig | null>(null);
  const [estado, setEstado] = useState<EstadoPush>('carregando');
  const [ocupado, setOcupado] = useState(false);
  const [recado, setRecado] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;

    fetchPushConfig()
      .then(async (c) => {
        if (!ativo) return;
        setConfig(c);

        if (!c.enabled || !suportaPush) {
          setEstado('indisponivel');
          return;
        }
        if (Notification.permission === 'denied') {
          setEstado('negado');
          return;
        }

        // A conta pode ter outro aparelho inscrito; o que decide o estado
        // desta tela é a inscrição *deste* navegador.
        const registro = await navigator.serviceWorker.getRegistration();
        const inscricao = await registro?.pushManager.getSubscription();
        if (ativo) setEstado(inscricao ? 'ligado' : 'desligado');
      })
      .catch(() => ativo && setEstado('indisponivel'));

    return () => {
      ativo = false;
    };
  }, []);

  const ligar = useCallback(async (): Promise<boolean> => {
    if (!config?.public_key) return false;
    setOcupado(true);
    setRecado(null);
    try {
      const permissao = await Notification.requestPermission();
      if (permissao !== 'granted') {
        setEstado(permissao === 'denied' ? 'negado' : 'desligado');
        return false;
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
      return true;
    } catch {
      setRecado('Não consegui ativar agora. Tente de novo em instantes.');
      return false;
    } finally {
      setOcupado(false);
    }
  }, [config]);

  const desligar = useCallback(async () => {
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
  }, []);

  const testar = useCallback(async () => {
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
  }, []);

  return { config, estado, ocupado, recado, ligar, desligar, testar };
}
