import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { DoneEventsProvider } from './contexts/DoneEventsContext';
import './index.css';

/*
  Service worker: só no build de produção. Em desenvolvimento ele serviria a
  casca guardada por cima do hot reload do Vite, e toda alteração pareceria não
  ter efeito — armadilha clássica de PWA.

  Registrado depois do `load` para não disputar banda com o primeiro
  carregamento, que é justamente o que precisa ser rápido no 4G. Falhar aqui é
  irrelevante: sem service worker o app continua funcionando como site.
*/
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* navegador sem suporte, aba anônima ou HTTP: segue como site normal */
    });
  });
}

/*
  O navegador guarda onde a página estava e devolve o scroll no reload. Isso
  serve para página de conteúdo, e atrapalha aqui: o app abre com o esqueleto
  (curto), a agenda chega depois e cresce, e o Safari aplica a posição velha
  em cima do conteúdo novo — o aluno abre o ícone da tela inicial e cai no meio
  da lista, sem entender por quê. Quem decide a posição é o App, que rola para
  o topo quando a agenda termina de carregar.
*/
if ('scrollRestoration' in history) {
  history.scrollRestoration = 'manual';
}

// Ponto de entrada do React — monta a aplicação no elemento #root do index.html
ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <DoneEventsProvider>
      <App />
    </DoneEventsProvider>
  </React.StrictMode>
);
