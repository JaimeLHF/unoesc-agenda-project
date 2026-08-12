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

      {/*
        Aviso antes do campo de senha, não depois: o aluno precisa saber o que
        acontece com a credencial dele antes de digitá-la. O texto diz o que o
        sistema faz de verdade — guarda a senha cifrada — porque a alternativa
        seria pedir a senha de novo várias vezes ao dia.
      */}
      <div className="privacy-notice">
        <strong>Antes de continuar:</strong> guardamos sua senha de forma cifrada no
        servidor para manter você conectado ao Moodle durante o uso. Ela nunca fica
        salva no seu navegador e não é compartilhada com ninguém. Você pode apagar
        tudo a qualquer momento em <em>Excluir conta</em>.
        <br />
        Este é um projeto independente, feito por alunos. Não é um serviço oficial da
        UNOESC.
      </div>

      <form onSubmit={handleSubmit} className="login-form">
        <div className="form-group">
          <label htmlFor="username">Usuário do Moodle</label>
          <input
            id="username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="sua matrícula@unoesc.edu.br"
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
              <span className="spinner" aria-hidden="true" /> Entrando…
            </>
          ) : (
            'Entrar e ver minha agenda'
          )}
        </button>
      </form>
    </div>
  );
};

export default LoginForm;
