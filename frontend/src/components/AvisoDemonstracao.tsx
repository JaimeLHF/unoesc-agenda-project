import React from 'react';
import Icon from './Icon';

interface AvisoDemonstracaoProps {
  onSair: () => void;
}

/**
 * A faixa que acompanha a agenda de exemplo.
 *
 * Ela existe por dois motivos, e o segundo é o que a mantém no topo e não no
 * rodapé: dizer que **nada ali é dado de verdade** — uma agenda que parece a
 * do aluno e não é seria a pior primeira impressão possível — e oferecer o
 * caminho de saída no mesmo lugar onde ele acabou de se convencer.
 *
 * Não fecha. Um "x" transformaria a demonstração numa tela indistinguível da
 * agenda real assim que a pessoa clicasse.
 */
const AvisoDemonstracao: React.FC<AvisoDemonstracaoProps> = ({ onSair }) => (
  <div className="demo-banner" role="status">
    <span className="demo-banner__texto">
      <Icon name="alerta" size={1} />
      <span>
        <strong>Exemplo</strong> — disciplinas e datas inventadas, só para você ver
        como a agenda funciona.
      </span>
    </span>
    <button type="button" className="btn-primary demo-banner__acao" onClick={onSair}>
      Entrar com minha conta
    </button>
  </div>
);

/**
 * O que a agenda de exemplo não consegue mostrar.
 *
 * A demonstração prova a parte visível — a lista, os selos, a semana. Assistente,
 * notificação e calendário assinável dependem de uma conta de verdade, e fingir
 * qualquer um deles com tela falsa seria prometer o que a pessoa não viu
 * funcionando. Então eles são ditos em três linhas, no fim da rolagem, onde
 * quem chegou até aqui já está decidindo.
 */
export const RecursosDaDemonstracao: React.FC<AvisoDemonstracaoProps> = ({ onSair }) => (
  <section className="demo-extras">
    <h2 className="demo-extras__titulo">E ainda tem, quando você entra com a sua conta</h2>

    <ul className="demo-extras__lista">
      <li>
        <Icon name="ia" size={1.1} />
        <div>
          <strong>Lumi, a assistente</strong>
          <p>Pergunte “por onde eu começo?” e receba um plano em até cinco linhas.</p>
        </div>
      </li>
      <li>
        <Icon name="sino" size={1.1} />
        <div>
          <strong>Avisos no celular</strong>
          <p>Saiu nota, o professor mudou a data, a webconferência começa em duas horas — com o app fechado.</p>
        </div>
      </li>
      <li>
        <Icon name="calendario" size={1.1} />
        <div>
          <strong>Sua agenda no calendário</strong>
          <p>Um endereço para assinar no Google Agenda ou no Calendário do iPhone.</p>
        </div>
      </li>
    </ul>

    <button type="button" className="btn-primary demo-extras__acao" onClick={onSair}>
      Entrar com minha conta do Moodle
    </button>
  </section>
);

export default AvisoDemonstracao;
