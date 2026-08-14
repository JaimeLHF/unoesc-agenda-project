import React, { useEffect, useRef, useState } from 'react';
import Icon from './Icon';

interface AppHeaderProps {
  /** Sem sessão, a barra mostra só a marca — não há conta para agir sobre. */
  authenticated: boolean;
  username?: string | null;
  onRefresh: () => void;
  refreshing: boolean;
  onOpenAssistant?: () => void;
  assistantAvailable?: boolean;
  onClearCache: () => void;
  onLogout: () => void;
  onDeleteAccount: () => void;
}

/**
 * Barra superior do app.
 *
 * Antes era um bloco azul de 100px com o título centralizado e um emoji: ocupava
 * a melhor faixa da tela para repetir um nome que o aluno já sabe. Agora é uma
 * faixa fina que fica fixa no topo e carrega o que muda — quem está logado e as
 * ações da conta —, deixando o azul como sotaque da marca em vez de fundo.
 *
 * Atualizar, Limpar cache, Sair e Excluir conta moraram na lista de disciplinas
 * até aqui. São ações de conta, não de lista: apareciam de novo em cada tela e
 * disputavam atenção com o conteúdo.
 */
const AppHeader: React.FC<AppHeaderProps> = ({
  authenticated,
  username,
  onRefresh,
  refreshing,
  onOpenAssistant,
  assistantAvailable,
  onClearCache,
  onLogout,
  onDeleteAccount,
}) => {
  const [menuAberto, setMenuAberto] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Fecha no Esc e no clique fora — um menu que só fecha no próprio botão
  // deixa o aluno preso quando ele clica em qualquer outro lugar.
  useEffect(() => {
    if (!menuAberto) return;
    const noEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuAberto(false);
    };
    const foraDoMenu = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuAberto(false);
      }
    };
    document.addEventListener('keydown', noEsc);
    document.addEventListener('mousedown', foraDoMenu);
    return () => {
      document.removeEventListener('keydown', noEsc);
      document.removeEventListener('mousedown', foraDoMenu);
    };
  }, [menuAberto]);

  const executar = (acao: () => void) => () => {
    setMenuAberto(false);
    acao();
  };

  return (
    <header className="topbar">
      <div className="topbar__inner">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <Icon name="marca" size={1.35} />
          </span>
          <span className="brand__text">
            <span className="brand__name">Agenda UNOESC</span>
            <span className="brand__tagline">Entregas, provas e webconferências</span>
          </span>
        </div>

        {authenticated && (
          <div className="topbar__actions">
            {username && (
              <span className="topbar__user" title={username}>
                {username}
              </span>
            )}

            {assistantAvailable && onOpenAssistant && (
              <button
                type="button"
                className="btn-ghost"
                onClick={onOpenAssistant}
                title="Pedir ajuda para organizar seus prazos"
              >
                <Icon name="organizar" />
                <span className="btn-ghost__label">Organizar</span>
              </button>
            )}

            <button
              type="button"
              className="btn-ghost"
              onClick={onRefresh}
              disabled={refreshing}
              title="Buscar disciplinas e eventos novamente no Moodle"
            >
              {refreshing ? (
                <span className="spinner spinner--dark" aria-hidden="true" />
              ) : (
                <Icon name="atualizar" />
              )}
              <span className="btn-ghost__label">
                {refreshing ? 'Atualizando…' : 'Atualizar'}
              </span>
            </button>

            <div className="account-menu" ref={menuRef}>
              <button
                type="button"
                className="btn-icon"
                onClick={() => setMenuAberto((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={menuAberto}
              >
                <Icon name="menu" label="Opções da conta" />
              </button>

              {menuAberto && (
                <div className="account-menu__panel" role="menu">
                  <button
                    type="button"
                    role="menuitem"
                    className="account-menu__item"
                    onClick={executar(onClearCache)}
                  >
                    <Icon name="limpar" />
                    Limpar dados salvos
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="account-menu__item"
                    onClick={executar(onLogout)}
                  >
                    <Icon name="sair" />
                    Sair
                  </button>
                  <div className="account-menu__separator" />
                  <button
                    type="button"
                    role="menuitem"
                    className="account-menu__item account-menu__item--danger"
                    onClick={executar(onDeleteAccount)}
                  >
                    <Icon name="lixeira" />
                    Excluir conta
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );
};

export default AppHeader;
