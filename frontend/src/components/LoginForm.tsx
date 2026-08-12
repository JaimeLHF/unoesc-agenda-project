import React, { useState } from 'react';
import type { LoginCredentials } from '../types';

interface LoginFormProps {
  onSubmit: (credentials: LoginCredentials) => void;
  loading: boolean;
  error: string | null;
}

/**
 * Formulário de login com as credenciais do portal UNOESC.
 * Exibe estado de carregamento e mensagem de erro quando necessário.
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
    <div className="login-card">
      <h2 className="login-title">Entre com sua conta do Moodle</h2>
      <p className="login-subtitle">
        Use o mesmo usuário e senha do <strong>on.unoesc.edu.br</strong>. Em alguns
        segundos suas entregas, provas e webconferências aparecem numa lista só.
      </p>

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
          {/*
            A dúvida mais comum de quem entra pela primeira vez é o formato do
            usuário — só o código não funciona, o domínio faz parte do login.
          */}
          <small className="form-hint">
            É o seu código de aluno com o domínio:{' '}
            <code>&lt;codigo_aluno&gt;@unoesc.edu.br</code>
          </small>

          <details className="form-help">
            <summary>Como encontrar meu código de aluno?</summary>
            <p>
              É o número da sua matrícula na UNOESC — o mesmo que você usa para entrar
              no Moodle e no portal acadêmico.
            </p>
          </details>
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
            ⚠️ {error}
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
        Aviso de privacidade no rodapé do card, discreto mas ainda na mesma
        tela do campo de senha — o aluno precisa poder ler o que acontece com
        a credencial dele sem sair daqui.
      */}
      <p className="login-footnote">
        Guardamos sua senha cifrada no servidor para manter você conectado ao Moodle
        durante o uso; ela nunca fica salva no navegador. Você apaga tudo quando quiser
        em <em>Excluir conta</em>.
      </p>
    </div>
  );
};

export default LoginForm;
