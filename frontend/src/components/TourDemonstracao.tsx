import React, { useCallback, useEffect, useState } from 'react';

interface Passo {
  /** Seletor do que fica aceso. Passo cujo alvo não existe na tela é pulado. */
  seletor: string;
  titulo: string;
  texto: string;
  /**
   * Botão da própria tela a ser clicado antes de acender o alvo. É como o
   * passo da visão por semana mostra os selos de que ele fala: em vez de
   * descrever uma tela que a pessoa teria de achar sozinha, a apresentação
   * troca a visão na frente dela. Só clica no que já está na tela — não há
   * atalho para dentro dos componentes.
   */
  clicarAntes?: string;
}

/*
  A ordem é a da leitura da tela, de cima para baixo, e não a da importância:
  um tour que salta do topo para o rodapé e volta faz a pessoa perder de vista
  onde ela está. Cada passo fala de uma coisa só.
*/
const PASSOS: Passo[] = [
  {
    seletor: '.proximo',
    titulo: 'O que vence primeiro',
    texto:
      'Abrindo o app, a primeira coisa na tela é o compromisso mais próximo — com quanto tempo falta e a barra andando até lá.',
  },
  {
    seletor: '.semana-cheia',
    titulo: 'Quando a semana aperta',
    texto:
      'A agenda conta os próximos sete dias e avisa antes: três compromissos ou duas provas já viram este alerta.',
  },
  {
    seletor: '.alerts-section',
    titulo: 'Tudo o que vem, em ordem',
    texto:
      'Entregas, provas e webconferências de todas as disciplinas numa lista só — sem abrir sala por sala no Moodle.',
  },
  {
    seletor: '.semana',
    titulo: 'A semana dia a dia',
    texto:
      'Aqui aparecem os selos: "Adiado" quando o professor muda a data, "PDF" quando ela veio do plano de ensino, e quanto a avaliação vale.',
    clicarAntes: '.visao__botao:first-child',
  },
  {
    // A grade inteira, não um cartão: os selos de que este passo fala estão
    // em cartões diferentes, e acender só o primeiro apagava justamente eles.
    seletor: '.subject-grid-large',
    titulo: 'Cada disciplina, com nota e novidades',
    texto:
      'O cartão mostra a nota assim que ela sai e marca o que o professor publicou na sala desde a sua última visita.',
    clicarAntes: '.visao__botao:last-child',
  },
  {
    seletor: '.demo-extras',
    titulo: 'E o que só a sua conta liga',
    texto:
      'Assistente, avisos no celular e o link para assinar a agenda no calendário do seu telefone.',
  },
];

interface TourDemonstracaoProps {
  onFim: () => void;
}

interface Foco {
  top: number;
  left: number;
  width: number;
  height: number;
  /** O balão cabe embaixo do alvo? Senão ele vai para cima. */
  abaixo: boolean;
}

const RESPIRO = 8;
const LARGURA_BALAO = 330;

/**
 * A apresentação guiada que roda por cima da agenda de exemplo.
 *
 * Escrita à mão, sem biblioteca de tour: o que elas trazem de útil aqui são
 * seis balões e um recorte, e o público deste app abre a agenda no 4G — a
 * regra de não adicionar dependência ao frontend vale principalmente para a
 * primeira tela que alguém vê.
 *
 * O recorte não é um buraco de verdade: é uma `box-shadow` gigante em volta de
 * um retângulo transparente, que escurece tudo menos o alvo com um elemento
 * só. Por cima da página fica uma folha invisível que engole os cliques —
 * durante a apresentação, clicar num cartão levaria a pessoa para outra tela
 * com o balão falando de uma coisa que já não está ali.
 *
 * Passo cujo alvo não existe é pulado sem aparecer: a demonstração muda com o
 * calendário (semana sem nada não desenha o alerta de semana cheia), e um
 * balão apontando para o vazio é pior que um passo a menos.
 */
const TourDemonstracao: React.FC<TourDemonstracaoProps> = ({ onFim }) => {
  const [indice, setIndice] = useState(0);
  const [foco, setFoco] = useState<Foco | null>(null);

  const passo = PASSOS[indice];

  /** Mede o alvo do passo atual. Devolve `false` quando ele não está na tela. */
  const medir = useCallback((): boolean => {
    const alvo = document.querySelector(passo?.seletor ?? '');
    if (!alvo) return false;

    const r = alvo.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;

    setFoco({
      top: r.top - RESPIRO,
      left: r.left - RESPIRO,
      width: r.width + RESPIRO * 2,
      height: r.height + RESPIRO * 2,
      // Metade de cima da janela: sobra espaço embaixo para o balão.
      abaixo: r.top + r.height / 2 < window.innerHeight / 2,
    });
    return true;
  }, [passo]);

  // Traz o alvo para o meio da tela e mede. O scroll é instantâneo de
  // propósito: medir no meio de uma rolagem suave dá um retângulo que já
  // mudou de lugar quando o balão aparece.
  useEffect(() => {
    if (!passo) {
      onFim();
      return;
    }

    if (passo.clicarAntes) {
      document.querySelector<HTMLElement>(passo.clicarAntes)?.click();
    }

    /*
      Procurar o alvo no mesmo tick do clique acima devolvia a tela anterior —
      o React ainda não tinha trocado a visão —, e o passo era descartado como
      se o alvo não existisse. Dois frames: um para o React pintar, outro para
      o layout assentar antes da medida.
    */
    let vivo = true;
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        if (!vivo) return;
        const alvo = document.querySelector(passo.seletor);
        if (!alvo) {
          setIndice((i) => i + 1);
          return;
        }
        alvo.scrollIntoView({ block: 'center', behavior: 'auto' });
        if (!medir()) setIndice((i) => i + 1);
      });
    });

    const remedir = () => {
      medir();
    };
    window.addEventListener('resize', remedir);
    window.addEventListener('scroll', remedir, { passive: true });
    return () => {
      vivo = false;
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', remedir);
      window.removeEventListener('scroll', remedir);
    };
  }, [passo, medir, onFim]);

  // Esc sai — é o gesto que todo mundo tenta antes de procurar o "Pular".
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onFim();
    };
    window.addEventListener('keydown', aoTeclar);
    return () => window.removeEventListener('keydown', aoTeclar);
  }, [onFim]);

  if (!passo || !foco) return null;

  const ultimo = indice === PASSOS.length - 1;
  const larguraBalao = Math.min(LARGURA_BALAO, window.innerWidth - 32);
  const esquerda = Math.min(
    Math.max(foco.left, 16),
    Math.max(16, window.innerWidth - larguraBalao - 16),
  );

  const posicaoBalao: React.CSSProperties = foco.abaixo
    ? { top: foco.top + foco.height + 12, left: esquerda, width: larguraBalao }
    : {
        bottom: window.innerHeight - foco.top + 12,
        left: esquerda,
        width: larguraBalao,
      };

  return (
    <div className="tour">
      {/* Engole os cliques na página enquanto a apresentação está no ar. */}
      <div className="tour__folha" aria-hidden="true" />

      <div
        className="tour__foco"
        aria-hidden="true"
        style={{
          top: foco.top,
          left: foco.left,
          width: foco.width,
          height: foco.height,
        }}
      />

      <div
        className="tour__balao"
        style={posicaoBalao}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-titulo"
      >
        <p className="tour__contador">
          {indice + 1} de {PASSOS.length}
        </p>
        <h2 className="tour__titulo" id="tour-titulo">
          {passo.titulo}
        </h2>
        <p className="tour__texto">{passo.texto}</p>

        <div className="tour__acoes">
          <button type="button" className="btn-ghost tour__pular" onClick={onFim}>
            Pular
          </button>
          <button
            type="button"
            className="btn-primary tour__proximo"
            /* O foco automático fica no botão que avança: quem usa teclado
               atravessa a apresentação só no Enter. */
            autoFocus
            onClick={() => (ultimo ? onFim() : setIndice(indice + 1))}
          >
            {ultimo ? 'Ver a agenda' : 'Próximo'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default TourDemonstracao;
