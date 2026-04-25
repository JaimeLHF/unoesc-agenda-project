/**
 * Estado de "concluídos" persistido no backend (SQLite).
 *
 * Cada `AcademicEvent` recebe um `id` UUID novo a cada scraping, então
 * usamos uma chave estável composta de (disciplina + data + título) que
 * sobrevive entre execuções.
 */

import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { AcademicEvent } from '../types';
import { markEventDone, unmarkEventDone } from '../services/api';

interface DoneEventsContextValue {
  isDone: (event: AcademicEvent) => boolean;
  toggleDone: (event: AcademicEvent) => void;
  /** Inicializa o conjunto a partir do backend. Chamado após login/cache load. */
  hydrate: (keys: string[]) => void;
  doneCount: number;
}

const DoneEventsContext = createContext<DoneEventsContextValue | null>(null);

/** Chave estável entre sessões (mesma fórmula do backend). */
export function eventKey(event: AcademicEvent): string {
  return `${event.subject}|${event.date}|${event.title}`.toLowerCase().trim();
}

export const DoneEventsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [doneKeys, setDoneKeys] = useState<Set<string>>(new Set());

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

      const action = wasDone ? unmarkEventDone(key) : markEventDone(key);
      action
        .then((serverKeys) => setDoneKeys(new Set(serverKeys)))
        .catch((err) => {
          console.error('Falha ao salvar status de concluído:', err);
          // Reverte no erro
          setDoneKeys((prev) => {
            const next = new Set(prev);
            if (wasDone) next.add(key);
            else next.delete(key);
            return next;
          });
        });
    },
    [doneKeys],
  );

  const value = useMemo<DoneEventsContextValue>(
    () => ({ isDone, toggleDone, hydrate, doneCount: doneKeys.size }),
    [isDone, toggleDone, hydrate, doneKeys],
  );

  return <DoneEventsContext.Provider value={value}>{children}</DoneEventsContext.Provider>;
};

export function useDoneEvents(): DoneEventsContextValue {
  const ctx = useContext(DoneEventsContext);
  if (!ctx) throw new Error('useDoneEvents deve ser usado dentro de <DoneEventsProvider>');
  return ctx;
}
