import { useEffect, useState } from 'react';

/*
 * O que a tela diz enquanto o Moodle não responde.
 *
 * "Buscando seus dados no Moodle…" ficava parado por até um minuto na
 * primeira busca, e frase que não muda por um minuto parece app travado — o
 * esqueleto pulsa, o texto não, e quem olha não sabe se ainda está andando.
 *
 * As frases seguem a ordem real do `run()` em `backend/app/moodle.py`: login,
 * lista de disciplinas, calendário, a sala de cada disciplina, notas. Não é
 * enfeite — é o único lugar onde o aluno vê em que pé está uma espera que
 * acontece inteira do lado do servidor. Se aquela ordem mudar, esta lista
 * muda junto, senão vira mentira educada.
 *
 * Elas têm comprimento parecido de propósito: o status é uma pílula que se
 * ajusta ao texto, e frases de tamanhos muito diferentes fariam a pílula
 * pular a cada troca.
 */
export const FRASES_CARREGANDO = [
  'Entrando no Moodle…',
  'Buscando suas disciplinas…',
  'Lendo o calendário…',
  'Abrindo as salas…',
  'Conferindo notas…',
  'Montando sua agenda…',
] as const;

/** Quanto cada frase fica na tela. */
const INTERVALO_MS = 3500;

/**
 * A frase da vez. Avança sozinha e **para na última**: voltar a "Entrando no
 * Moodle…" aos 40 segundos diria que o app recomeçou, e ele não recomeçou —
 * uma busca longa é uma busca longa, não um laço.
 *
 * `ativo` em `false` devolve a primeira frase e zera o relógio, para a próxima
 * espera começar do começo em vez de continuar de onde a anterior parou.
 */
export function useFraseCarregando(ativo = true): string {
  const [indice, setIndice] = useState(0);

  useEffect(() => {
    if (!ativo) setIndice(0);
  }, [ativo]);

  // Um `setTimeout` por frase, e não um `setInterval` que se cancela sozinho:
  // parar no fim vira a própria condição de saída do efeito, sem efeito
  // colateral dentro do `setIndice` (que o StrictMode roda duas vezes).
  useEffect(() => {
    if (!ativo || indice >= FRASES_CARREGANDO.length - 1) return;
    const id = window.setTimeout(() => setIndice(indice + 1), INTERVALO_MS);
    return () => window.clearTimeout(id);
  }, [ativo, indice]);

  return FRASES_CARREGANDO[indice];
}
