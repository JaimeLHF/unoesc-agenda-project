import React from 'react';
import Icon from './Icon';

interface InstalarNoCelularProps {
  /** Versão enxuta, sem título de seção — usada na tela de login. */
  compacto?: boolean;
}

/**
 * Como levar a agenda para a tela inicial do celular.
 *
 * O QR é um SVG estático em `public/`, não um gerador em JavaScript: o
 * endereço do app nunca muda, então gerar o mesmo desenho a cada carregamento
 * seria pagar biblioteca no bundle para produzir um arquivo constante.
 *
 * O código só aparece em tela larga. Quem já está no celular não tem como
 * apontar a câmera para a própria tela — para esse aluno o que serve é o passo
 * a passo, que fica visível nos dois tamanhos.
 */
const InstalarNoCelular: React.FC<InstalarNoCelularProps> = ({ compacto = false }) => (
  <div className={`instalar${compacto ? ' instalar--compacto' : ''}`}>
    <div className="instalar__qr">
      {/*
        Fundo branco fixo, mesmo no tema escuro: leitor de QR precisa de
        contraste entre o desenho e o fundo, e azul sobre cinza-chumbo não lê.
      */}
      <img
        src="/qr-instalar.svg"
        alt="Código QR que abre unoesc-agenda.fly.dev"
        width={140}
        height={140}
      />
      <span className="instalar__qr-legenda">Aponte a câmera do celular</span>
    </div>

    <div className="instalar__texto">
      {!compacto && (
        <h3 className="instalar__titulo">
          <Icon name="calendario" size={1} />
          Instalar no celular
        </h3>
      )}
      <p className="instalar__intro">
        A agenda vira um ícone na tela inicial e abre em tela cheia, sem a barra do
        navegador.
      </p>
      <ul className="instalar__passos">
        <li>
          <strong>Android:</strong> abra no Chrome e toque em “Instalar app”, no menu.
        </li>
        <li>
          <strong>iPhone:</strong> abra no <strong>Safari</strong>, toque em Compartilhar
          e depois em “Adicionar à Tela de Início”. No Chrome do iPhone a opção não
          existe.
        </li>
      </ul>
    </div>
  </div>
);

export default InstalarNoCelular;
