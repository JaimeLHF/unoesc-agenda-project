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
      <h2 className="login-title">Acesse o Portal UNOESC</h2>
      <p className="login-subtitle">
        Suas credenciais são usadas apenas para acessar o portal e nunca são armazenadas.
      </p>

      <form onSubmit={handleSubmit} className="login-form">
        <div className="form-group">
          <label htmlFor="username">Usuário (matrícula / CPF)</label>
          <input
            id="username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Digite seu usuário"
            disabled={loading}
            required
            autoComplete="username"
            className="input-blurred"
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
              <span className="spinner" aria-hidden="true" /> Buscando atividades…
            </>
          ) : (
            '🔍 Buscar Atividades'
          )}
        </button>
      </form>
    </div>
  );
};

export default LoginForm;
