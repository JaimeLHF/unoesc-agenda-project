import React from 'react';
import { useFraseCarregando } from '../lib/frasesCarregando';

interface LoadingSkeletonProps {
  /**
   * Aviso curto no topo, ao lado do spinner. Sem ele o esqueleto narra a
   * busca sozinho, trocando de frase conforme o tempo passa
   * (`frasesCarregando`) — que é o caso da agenda. Passar um texto fixo aqui
   * é para a espera que tem um nome só.
   */
  status?: string;
  /** Aparece abaixo do esqueleto; some quando não há nada a dizer. */
  message?: string;
  /** Quantos cartões falsos desenhar. */
  cards?: number;
}

/**
 * O que a tela mostra enquanto a agenda ainda não chegou do Moodle.
 *
 * Desenha a forma da tela de resultados — cabeçalho, faixa de alertas e a
 * grade de disciplinas — em blocos cinza. Um spinner sozinho não diz nada
 * sobre o que está vindo; o esqueleto já ensina o layout, e quando os dados
 * entram nada salta de lugar.
 *
 * Enquanto ele está no ar, mais nada é renderizado: meia agenda desatualizada
 * é pior que nenhuma, porque o aluno não tem como saber qual metade é velha.
 */
const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({ status, message, cards = 6 }) => {
  // O hook é chamado sempre (regra dos hooks) e fica parado quando veio um
  // texto pronto de fora.
  const frase = useFraseCarregando(!status);
  const texto = status ?? frase;

  return (
  <section className="skeleton" aria-busy="true" aria-label="Carregando sua agenda">
    {/* O aviso vem antes dos blocos: sem ele, seis cartões cinza pulsando não
        dizem se o app está trabalhando ou se deu erro.

        `aria-hidden` porque o texto troca sozinho: num leitor de tela isso
        seria uma interrupção a cada três segundos e meio para dizer o que o
        `aria-label` da seção já disse uma vez. */}
    <p className="skeleton__status" aria-hidden="true">
      <span className="spinner spinner--dark" aria-hidden="true" />
      {/* `key` na frase reinicia a animação de entrada a cada troca. */}
      <span key={texto} className="skeleton__frase">
        {texto}
      </span>
    </p>

    <div className="skeleton__heading" aria-hidden="true">
      <div className="skeleton__bar skeleton__bar--title" />
      <div className="skeleton__bar skeleton__bar--subtitle" />
    </div>

    <div className="skeleton__pills" aria-hidden="true">
      <div className="skeleton__pill" />
      <div className="skeleton__pill skeleton__pill--wide" />
      <div className="skeleton__pill" />
    </div>

    <div className="skeleton__grid" aria-hidden="true">
      {Array.from({ length: cards }, (_, i) => (
        <div key={i} className="skeleton__card">
          <div className="skeleton__bar skeleton__bar--card-title" />
          <div className="skeleton__bar skeleton__bar--card-meta" />
          <div className="skeleton__card-footer">
            <div className="skeleton__bar skeleton__bar--card-next" />
          </div>
        </div>
      ))}
    </div>

    {message && <p className="skeleton__message">{message}</p>}
  </section>
  );
};

export default LoadingSkeleton;
