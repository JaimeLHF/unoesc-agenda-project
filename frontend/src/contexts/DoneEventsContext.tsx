/**
 * Estado de "concluídos" persistido no backend (SQLite).
 *
 * Cada `AcademicEvent` recebe um `id` UUID novo a cada scraping, então
 * usamos uma chave estável composta de (disciplina + data + título) que
 * sobrevive entre execuções.
 */

/* eslint-disable react-refresh/only-export-components --
   Padrão de contexto do React: além do provider, o arquivo exporta o hook
   `useDoneEvents` e o helper `eventKey`. Quebrar em três arquivos só para
   agradar o fast refresh espalharia o contexto sem ganho real — o custo é
   um reload a mais ao editar este arquivo durante o desenvolvimento. */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { AcademicEvent } from '../types';
import Icon from '../components/Icon';
import { markEventDone, unmarkEventDone } from '../services/api';

interface DoneEventsContextValue {
  isDone: (event: AcademicEvent) => boolean;
  toggleDone: (event: AcademicEvent) => void;
  /** Inicializa o conjunto a partir do backend. Chamado após login/cache load. */
  hydrate: (keys: string[]) => void;
  doneCount: number;
}

const DoneEventsContext = createContext<DoneEventsContextValue | null>(null);

/**
 * Chave estável entre sessões.
 *
 * O backend manda `stable_key` pronto (derivado do id do evento no Moodle) —
 * usar esse valor evita manter duas fórmulas idênticas na mão, uma aqui e uma
 * no Python. O fallback cobre eventos guardados antes dessa mudança.
 */
export function eventKey(event: AcademicEvent): string {
  return (
    event.stable_key ??
    `${event.subject}|${event.date}|${event.title}`.toLowerCase().trim()
  );
}

/** Quanto tempo o aviso de desfazer fica na tela. */
const DESFAZER_MS = 7000;

export const DoneEventsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [doneKeys, setDoneKeys] = useState<Set<string>>(new Set());

  /**
   * A última atividade marcada como concluída, enquanto o desfazer está de pé.
   *
   * Marcar tira o item da vista em mais de um lugar — some da faixa de alertas
   * e some do detalhe quando "Ocultar concluídos" está ligado. Sem esta faixa,
   * desmarcar um clique errado exigia ir caçar a atividade de volta.
   */
  const [desfazivel, setDesfazivel] = useState<AcademicEvent | null>(null);
  const timer = useRef<number | null>(null);

  const agendarSumico = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setDesfazivel(null);
      timer.current = null;
    }, DESFAZER_MS);
  }, []);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  const hydrate = useCallback((keys: string[]) => {
    setDoneKeys(new Set(keys));
  }, []);

  const isDone = useCallback(
    (event: AcademicEvent) => doneKeys.has(eventKey(event)),
    [doneKeys],
  );

  const toggleDone = useCallback(
    (event: AcademicEvent) => {
      const key = eventKey(event);
      const wasDone = doneKeys.has(key);

      // Optimistic update — atualiza local antes da resposta do servidor
      setDoneKeys((prev) => {
        const next = new Set(prev);
        if (wasDone) next.delete(key);
        else next.add(key);
        return next;
      });

      // Desmarcar não precisa de aviso: o item volta para a vista sozinho, e
      // é a própria ação de desfazer.
      if (wasDone) {
        setDesfazivel(null);
      } else {
        setDesfazivel(event);
        agendarSumico();
      }

      const action = wasDone ? unmarkEventDone(key) : markEventDone(key);
      action
        .then((serverKeys) => setDoneKeys(new Set(serverKeys)))
        .catch((err) => {
          console.error('Falha ao salvar status de concluído:', err);
          // Reverte no erro — e some com o desfazer, que não tem mais o que
          // desfazer: no servidor a marcação nunca chegou a existir.
          setDesfazivel(null);
          setDoneKeys((prev) => {
            const next = new Set(prev);
            if (wasDone) next.add(key);
            else next.delete(key);
            return next;
          });
        });
    },
    [doneKeys, agendarSumico],
  );

  const value = useMemo<DoneEventsContextValue>(
    () => ({ isDone, toggleDone, hydrate, doneCount: doneKeys.size }),
    [isDone, toggleDone, hydrate, doneKeys],
  );

  return (
    <DoneEventsContext.Provider value={value}>
      {children}
      {desfazivel && (
        <div className="undo-toast" role="status">
          <span className="undo-toast__text">
            <strong>{desfazivel.title}</strong> marcada como concluída.
          </span>
          <button
            type="button"
            className="undo-toast__button"
            onClick={() => toggleDone(desfazivel)}
          >
            Desfazer
          </button>
          <button
            type="button"
            className="undo-toast__close"
            onClick={() => setDesfazivel(null)}
          >
            <Icon name="fechar" label="Fechar aviso" size={1} />
          </button>
        </div>
      )}
    </DoneEventsContext.Provider>
  );
};

export function useDoneEvents(): DoneEventsContextValue {
  const ctx = useContext(DoneEventsContext);
  if (!ctx) throw new Error('useDoneEvents deve ser usado dentro de <DoneEventsProvider>');
  return ctx;
}
