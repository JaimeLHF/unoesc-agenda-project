import React from 'react';

interface LoadingSkeletonProps {
  /** Aviso curto no topo, ao lado do spinner. Diz o que está acontecendo. */
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
const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({
  status = 'Buscando dados…',
  message,
  cards = 6,
}) => (
  <section className="skeleton" aria-busy="true" aria-live="polite">
    {/* O aviso vem antes dos blocos: sem ele, seis cartões cinza pulsando não
        dizem se o app está trabalhando ou se deu erro. */}
    <p className="skeleton__status">
      <span className="spinner spinner--dark" aria-hidden="true" />
      {status}
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

export default LoadingSkeleton;
