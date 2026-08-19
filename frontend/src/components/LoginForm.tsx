import React, { useRef, useState } from "react";
import Icon from "./Icon";
import InstalarNoCelular from "./InstalarNoCelular";
import type { LoginCredentials } from "../types";

interface LoginFormProps {
  /**
   * Devolve `true` quando entrou. É esse retorno que decide se a senha
   * digitada é apagada — um `error` novo não serve, porque errar a senha duas
   * vezes seguidas produz a mesma mensagem e o efeito não dispararia.
   */
  onSubmit: (credentials: LoginCredentials) => Promise<boolean>;
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
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const senhaRef = useRef<HTMLInputElement>(null);

  /*
    Login recusado apaga a senha e devolve o cursor para ela — o usuário fica
    escrito. Antes o formulário inteiro era desmontado durante a tentativa, e
    voltava vazio: quem errava a senha redigitava o e-mail junto, sem ter
    errado nada nele.
  */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;

    const entrou = await onSubmit({ username: username.trim(), password });
    if (!entrou) {
      setPassword('');
      // Depois do commit do React: enquanto `loading` era verdadeiro o campo
      // estava desabilitado, e `focus()` em campo desabilitado não faz nada.
      setTimeout(() => senhaRef.current?.focus(), 0);
    }
  };

  return (
    <div className="auth">
      <div className="auth__inner">
        {/* A marca abre a tela, centralizada e sobre as duas colunas. */}
        <div className="auth__brand">
          <span className="auth__mark" aria-hidden="true">
            <Icon name="marca" size={1.6} />
          </span>

          <h1 className="auth__title">Agenda UNOESC</h1>
          <p className="auth__subtitle">
            Entre com a sua conta do Moodle e veja as entregas, provas e
            webconferências de todas as disciplinas numa lista só.
          </p>
        </div>

        {/*
          Duas colunas em tela larga: à esquerda o que se lê uma vez (como
          instalar no celular), à direita o que se usa toda vez (os campos).
          Empilhado, a ordem inverte — quem abre no celular veio entrar, e o QR
          nem aparece nesse tamanho.
        */}
        <div className="auth__colunas">
          <aside className="auth__lado">
            <InstalarNoCelular compacto />
          </aside>

          <div className="auth__principal">
            {/*
            A dúvida mais comum de quem entra pela primeira vez é o formato do
            usuário — só o código não funciona, o domínio faz parte do login.
          */}
            <p className="auth__hint">
              Seu usuário é o código de aluno com o domínio:{" "}
              <code>&lt;codigo_aluno&gt;@unoesc.edu.br</code>
            </p>

            <details className="auth__help">
              <summary>Como encontrar meu código de aluno?</summary>
              <p>
                É o número da sua matrícula na UNOESC. Ele aparece no seu perfil
                dentro do Moodle e no portal acadêmico — abra um dos dois, copie
                o número e volte para cá.
              </p>
              <div className="auth__help-links">
                <a
                  href="https://on.unoesc.edu.br"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Icon name="link-externo" size={0.95} />
                  Abrir o Moodle
                </a>
                <a
                  href="https://acad.unoesc.edu.br"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Icon name="link-externo" size={0.95} />
                  Portal acadêmico
                </a>
              </div>
            </details>

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
                  ref={senhaRef}
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
                  "Entrar e ver minha agenda"
                )}
              </button>

              {/*
                A única frase que o rodapé da página não diz, e a que importa
                exatamente aqui: o que acontece com a senha que ele acabou de
                digitar. Autoria e "Privacidade e termos" ficam só no rodapé —
                estavam repetidos nesta mesma tela.
              */}
              <p className="auth__nota">
                Sua senha fica cifrada no servidor só para manter a conexão com o
                Moodle, e nunca é salva no navegador.
              </p>
            </form>
          </div>
        </div>

      </div>
    </div>
  );
};

export default LoginForm;
