import React, { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import { iniciais, primeiroNome } from '../lib/nome';
import ThemeToggle from './ThemeToggle';

interface AppHeaderProps {
  /** Sem sessão, a barra mostra só a marca — não há conta para agir sobre. */
  authenticated: boolean;
  username?: string | null;
  /** Nome do aluno no Moodle. Chega depois do login, junto com a foto. */
  fullName?: string | null;
  /** Foto do Moodle já embutida como `data:`; sem ela, entram as iniciais. */
  avatar?: string | null;
  onRefresh: () => void;
  refreshing: boolean;
  onOpenAssistant?: () => void;
  assistantAvailable?: boolean;
  onOpenProfile: () => void;
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
  fullName,
  avatar,
  onRefresh,
  refreshing,
  onOpenAssistant,
  assistantAvailable,
  onOpenProfile,
  onClearCache,
  onLogout,
  onDeleteAccount,
}) => {
  const [menuAberto, setMenuAberto] = useState(false);
  const [rolado, setRolado] = useState(false);
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

  /*
    A sombra só aparece quando há conteúdo passando por baixo. Parada no topo,
    a barra é parte da página; rolando, ela precisa se descolar do que desliza
    embaixo — a linha de 1px sozinha some quando um card branco encosta nela.
  */
  useEffect(() => {
    const aoRolar = () => setRolado(window.scrollY > 4);
    aoRolar();
    window.addEventListener('scroll', aoRolar, { passive: true });
    return () => window.removeEventListener('scroll', aoRolar);
  }, []);

  const executar = (acao: () => void) => () => {
    setMenuAberto(false);
    acao();
  };

  const nome = fullName || username || '';
  const rotuloPerfil = nome ? primeiroNome(nome) : 'Perfil';

  return (
    <header className={rolado ? 'topbar topbar--rolado' : 'topbar'}>
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

        <div className="topbar__actions">
          {/* Fora do bloco de conta de propósito: trocar o tema não depende
              de estar logado, e na tela de carregamento ele continua ali. */}
          <ThemeToggle />

          {authenticated && (
            <>
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

              {/*
                O rosto da conta abre o perfil. A matrícula que ficava aqui como
                texto morto ninguém reconhece de relance; a foto do Moodle, sim —
                e no celular ela é a única coisa que sobra, já do tamanho de um
                alvo de toque.
              */}
              <button
                type="button"
                className="topbar__profile"
                onClick={onOpenProfile}
                title={username ? `Perfil de ${username}` : 'Ver seu perfil'}
              >
                {avatar ? (
                  <img className="topbar__avatar" src={avatar} alt="" />
                ) : (
                  <span className="topbar__avatar topbar__avatar--iniciais" aria-hidden="true">
                    {iniciais(nome, username || '?')}
                  </span>
                )}
                <span className="topbar__profile-name">{rotuloPerfil}</span>
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
                    {/* Qual conta o menu vai mexer. As três ações abaixo apagam
                        ou encerram alguma coisa; vale dizer de quem. */}
                    {username && (
                      <>
                        <div className="account-menu__identity">
                          {nome !== username && <strong>{nome}</strong>}
                          <span>{username}</span>
                        </div>
                        <div className="account-menu__separator" />
                    </>
                  )}
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
            </>
          )}
        </div>
      </div>
    </header>
  );
};

export default AppHeader;
