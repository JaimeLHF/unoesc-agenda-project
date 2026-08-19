import React, { useState } from 'react';
import Icon from './Icon';
import InstalarNoCelular from './InstalarNoCelular';
import type { LoginCredentials } from '../types';

interface LoginFormProps {
  onSubmit: (credentials: LoginCredentials) => void;
  loading: boolean;
  error: string | null;
}

/**
 * Tela de entrada.
 *
 * Uma coluna, sem cartão e sem moldura: marca, uma frase, dois campos, um
 * botão. O cartão branco flutuando no fundo cinza dava à tela ar de produto de
 * empresa — este é um projeto de aluno, e a tela pode simplesmente dizer isso
 * em vez de vender alguma coisa.
 */
const LoginForm: React.FC<LoginFormProps> = ({ onSubmit, loading, error }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    onSubmit({ username: username.trim(), password });
  };

  return (
    <div className="auth">
      <div className="auth__inner">
        {/*
          Tudo o que é explicação fica no topo. No meio sobram só os dois campos
          e o botão — a dica de formato e o "como encontrar meu código" ficavam
          espremidos entre usuário e senha e quebravam o ritmo do formulário.
        */}
        <div className="auth__head">
          <span className="auth__mark" aria-hidden="true">
            <Icon name="marca" size={1.6} />
          </span>

          <h1 className="auth__title">Agenda UNOESC</h1>
          <p className="auth__subtitle">
            Entre com a sua conta do Moodle e veja as entregas, provas e webconferências
            de todas as disciplinas numa lista só.
          </p>

          {/*
            A dúvida mais comum de quem entra pela primeira vez é o formato do
            usuário — só o código não funciona, o domínio faz parte do login.
          */}
          <p className="auth__hint">
            Seu usuário é o código de aluno com o domínio:{' '}
            <code>&lt;codigo_aluno&gt;@unoesc.edu.br</code>
          </p>

          <details className="auth__help">
            <summary>Como encontrar meu código de aluno?</summary>
            <p>
              É o número da sua matrícula na UNOESC. Ele aparece no seu perfil dentro do
              Moodle e no portal acadêmico — abra um dos dois, copie o número e volte
              para cá.
            </p>
            <div className="auth__help-links">
              <a href="https://on.unoesc.edu.br" target="_blank" rel="noreferrer">
                <Icon name="link-externo" size={0.95} />
                Abrir o Moodle
              </a>
              <a href="https://acad.unoesc.edu.br" target="_blank" rel="noreferrer">
                <Icon name="link-externo" size={0.95} />
                Portal acadêmico
              </a>
            </div>
          </details>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="username">Usuário do Moodle</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="codigo_do_aluno@unoesc.edu.br"
              disabled={loading}
              required
              autoComplete="username"
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Senha</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Digite sua senha"
              disabled={loading}
              required
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div className="error-banner" role="alert">
              <Icon name="alerta" />
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn-primary"
            disabled={loading || !username.trim() || !password.trim()}
          >
            {loading ? (
              <>
                <span className="spinner" aria-hidden="true" /> Entrando…
              </>
            ) : (
              'Entrar e ver minha agenda'
            )}
          </button>
        </form>

        {/*
          Fica depois do formulário: quem chegou aqui veio entrar, não instalar.
          Só aparece em tela larga — no celular o aluno já está no lugar certo,
          e o próprio componente cuida disso.
        */}
        <InstalarNoCelular compacto />

        {/*
          Recado de quem fez, junto com o que acontece com a senha. Curto de
          propósito: o "não é serviço oficial" já está no rodapé logo abaixo, e
          repetir a mesma frase duas vezes na mesma tela só ocupa espaço.
        */}
        <p className="auth__signature">
          Feito por{' '}
          <a href="https://github.com/JaimeLHF" target="_blank" rel="noreferrer">
            Jaime Luiz Hansen Filho
          </a>
          , de Análise e Desenvolvimento de Sistemas na UNOESC São Miguel do Oeste. Sua
          senha fica cifrada no servidor só para manter a conexão com o Moodle e nunca é
          salva no navegador.{' '}
          <a href="/privacidade.html" target="_blank" rel="noreferrer">
            Privacidade e termos
          </a>
          .
        </p>
      </div>
    </div>
  );
};

export default LoginForm;
