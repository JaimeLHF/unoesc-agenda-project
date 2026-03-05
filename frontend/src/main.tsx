import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// Ponto de entrada do React — monta a aplicação no elemento #root do index.html
ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
