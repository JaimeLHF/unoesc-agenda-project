import React, { useEffect, useState } from 'react';
import ActivityPage from './components/ActivityPage';
import AppHeader from './components/AppHeader';
import Icon from './components/Icon';
import LoadingSkeleton from './components/LoadingSkeleton';
import AvisoNovidades from './components/AvisoNovidades';
import ConviteNotificacoes from './components/ConviteNotificacoes';
import LoginForm from './components/LoginForm';
import SubjectList from './components/SubjectList';
import SubjectDetail from './components/SubjectDetail';
import Assistant from './components/Assistant';
import AssistantFab from './components/AssistantFab';
import ProfilePage from './components/ProfilePage';
import AdminPage from './components/AdminPage';
import ThemeToggle from './components/ThemeToggle';
import {
  login,
  logout,
  isAuthenticated,
  scrapePortal,
  syncToCalendar,
  fetchCache,
  fetchAccount,
  fetchProfile,
  deleteAccount,
  clearCache,
  openCourse,
} from './services/api';
import type { Account, Profile } from './services/api';
import { requestGoogleAccessToken } from './services/googleAuth';
import { useDoneEvents, eventKey } from './contexts/DoneEventsContext';
import { ROTA_ADMIN, activityPath, navigate, useActivityRoute, useAdminRoute } from './lib/router';
import { agendaEstaFresca, compararAgendas } from './lib/novidades';
import type { Subject, AcademicEvent, LoginCredentials } from './types';
import './index.css';

type AppStep = 'login' | 'results' | 'assistant' | 'profile';

/**
 * O Google Calendar fica fora do ar enquanto a tela de consentimento OAuth não
 * passa pela verificação do Google (escopo sensível). Sem Client ID
 * configurado, os botões de sincronizar simplesmente não aparecem.
 */
const calendarEnabled = Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID);

const App: React.FC = () => {
  const [step, setStep] = useState<AppStep>('login');

  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [events, setEvents] = useState<AcademicEvent[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string | null>(null);
  const [lastScrapedAt, setLastScrapedAt] = useState<string | null>(null);
  // A senha não fica mais aqui: vai uma vez pro backend em /api/login, que
  // devolve um token guardado dentro de services/api. Aqui basta saber se a
  // sessão está ativa.
  const [authenticated, setAuthenticated] = useState(false);
  const [account, setAccount] = useState<Account | null>(null);
  // Só para a barra: nome e foto do aluno. Chega depois da agenda e sem
  // bloquear nada — se o Moodle não responder, a barra fica com as iniciais.
  const [profile, setProfile] = useState<Profile | null>(null);

  const [loginError, setLoginError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  /*
    A busca que acontece por baixo da agenda já na tela. É separada de
    `refreshing` de propósito: aquela é a espera que o aluno pediu (o botão
    "Atualizar"), esta ele nem sabe que começou — e por isso não pode mexer no
    scroll nem esconder o que está sendo lido.
  */
  const [atualizandoAoFundo, setAtualizandoAoFundo] = useState(false);
  /** O que chegou na última busca, para o aviso no topo da agenda. */
  const [novidades, setNovidades] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [backendOffline, setBackendOffline] = useState(false);

  const { hydrate } = useDoneEvents();

  // A atividade aberta mora no endereço, não no estado: assim o botão voltar
  // do navegador funciona e o link pode ser compartilhado com um colega.
  const activityKey = useActivityRoute();
  // O painel do dono também mora no endereço: ele precisa poder ser aberto
  // direto, sem passar pela agenda, e o backend responde 404 para quem não é.
  const naRotaAdmin = useAdminRoute();
  const abrirAtividade = (event: AcademicEvent) => navigate(activityPath(eventKey(event)));

  // Banner de "servidor fora do ar": axios interceptor dispatcha eventos
  // 'backend-online'/'backend-offline' a cada request.
  useEffect(() => {
    const onOnline = () => setBackendOffline(false);
    const onOffline = () => setBackendOffline(true);
    // O backend respondeu 401: o token caiu (expirou, ou o backend reiniciou).
    // Volta pro login em vez de deixar a tela travada em erro.
    const onSessionExpired = () => {
      setAuthenticated(false);
      setAccount(null);
      setProfile(null);
      setStep('login');
      setLoginError('Sua sessão expirou. Faça login novamente.');
    };
    window.addEventListener('backend-online', onOnline);
    window.addEventListener('backend-offline', onOffline);
    window.addEventListener('session-expired', onSessionExpired);
    return () => {
      window.removeEventListener('backend-online', onOnline);
      window.removeEventListener('backend-offline', onOffline);
      window.removeEventListener('session-expired', onSessionExpired);
    };
  }, []);

  // Não há mais carga de cache antes do login: num app multi-usuário o cache
  // pertence a alguém, e o backend precisa da sessão para saber a quem.

  /**
   * Busca disciplinas e eventos no Moodle e devolve o que veio — o retorno é
   * o que permite comparar com a agenda que já estava na tela e dizer o que
   * mudou.
   */
  const fetchAll = async () => {
    const scrapeResult = await scrapePortal();

    setSubjects(scrapeResult.subjects);
    setEvents(scrapeResult.calendar_events);
    setLastScrapedAt(new Date().toISOString());
    return { subjects: scrapeResult.subjects, events: scrapeResult.calendar_events };
  };

  /**
   * Vai ao Moodle sem tirar a agenda da tela, e anuncia o que voltou de lá.
   *
   * `anunciarVazio` liga o "sua agenda já está em dia": vale quando o aluno
   * apertou "Atualizar" e precisa saber que a busca terminou, e não vale na
   * busca que acontece sozinha ao abrir o app — ali, nada novo é para passar
   * despercebido mesmo.
   */
  const atualizarComparando = async (
    base: { subjects: Subject[]; events: AcademicEvent[] },
    anunciarVazio = false,
  ) => {
    const depois = await fetchAll();
    const { frase } = compararAgendas(base, depois);
    setNovidades(frase ?? (anunciarVazio ? 'Sua agenda já está em dia.' : null));
  };

  /** Login inicial — autentica e só abre a agenda depois de atualizá-la. */
  // Conferir a senha e carregar a agenda são duas esperas diferentes, e antes
  // as duas ligavam o mesmo sinalizador. O efeito era o aluno digitar a senha
  // errada e mesmo assim ver o esqueleto da agenda com "isso leva cerca de um
  // minuto", para só então voltar ao login — parecia que tinha entrado e sido
  // expulso. Agora o formulário fica na tela, com o botão girando, até o
  // backend aceitar a senha.
  const [loginLoading, setLoginLoading] = useState(false);
  const [abrindoAgenda, setAbrindoAgenda] = useState(false);

  /** `true` quando entrou; `false` deixa o formulário limpar a senha. */
  const handleLogin = async (creds: LoginCredentials): Promise<boolean> => {
    setLoginError(null);
    setLoginLoading(true);

    try {
      await login(creds);
    } catch (err: unknown) {
      setLoginLoading(false);
      setLoginError(mensagemDeErro(err));
      return false;
    }

    // Senha aceita: daqui para frente a espera é longa e tem o que mostrar.
    setLoginLoading(false);
    setAbrindoAgenda(true);

    try {
      await abrirSessao();
      setStep('results');
      return true;
    } catch (err: unknown) {
      setLoginError(mensagemDeErro(err));
      return false;
    } finally {
      setAbrindoAgenda(false);
    }
  };

  /**
   * Carrega conta, marcações e agenda de uma sessão já autenticada. Serve tanto
   * ao login quanto à retomada depois de um reload — o token vive no
   * `sessionStorage`, então recarregar a página não pede senha de novo.
   */
  const abrirSessao = async () => {
    {
      setAuthenticated(true);
      void fetchAccount().then(setAccount).catch(() => setAccount(null));
      void fetchProfile().then(setProfile).catch(() => setProfile(null));

      const cache = await fetchCache().catch(() => null);
      if (cache) hydrate(cache.doneKeys);
      const temCache = Boolean(cache && (cache.subjects.length > 0 || cache.events.length > 0));

      /*
        A agenda salva vai para a tela na hora.

        Isto já foi o contrário: o app segurava tudo no esqueleto até o Moodle
        responder, porque meia agenda velha numa tela de prazos é pior que
        nenhuma. O que faltava não era a espera, era o aluno saber em que pé
        estava — e agora ele sabe: o botão "Atualizar" gira enquanto a busca
        corre por baixo, e o que chegar é anunciado no topo. Esperar um minuto
        por uma agenda que quase sempre voltava igual era o preço mais alto.
      */
      if (cache && temCache) {
        setSubjects(cache.subjects);
        setEvents(cache.events);
        setLastScrapedAt(cache.lastScrapedAt);

        // Fechar e abrir o app não é motivo para outro login no Moodle: dentro
        // da janela de frescor, o que está na tela é o que o Moodle diria.
        if (!agendaEstaFresca(cache.lastScrapedAt)) {
          setAtualizandoAoFundo(true);
          void atualizarComparando({ subjects: cache.subjects, events: cache.events })
            .catch((err) => {
              // A tela já tem o que mostrar; o aviso diz de quando ela é.
              console.warn('Falha ao atualizar em segundo plano:', err);
              setRefreshError(
                'Não consegui falar com o Moodle agora. Esta é a sua última agenda salva.',
              );
            })
            .finally(() => setAtualizandoAoFundo(false));
        }
        return;
      }

      // Primeiro acesso: não há agenda salva, então não há o que mostrar antes
      // de o Moodle responder — aqui o esqueleto é a tela inteira, e falhar
      // devolve o login com o aviso. Quem já tem agenda nunca chega nesta
      // linha: saiu acima, com a lista na tela.
      await fetchAll();
    }
  };

  /*
    Retomada de sessão: com um token guardado, o reload volta direto para a
    agenda em vez de pedir a senha. O 401 do interceptor já cuida do token
    vencido — cai no `catch` e a tela de login volta com o aviso.
  */
  useEffect(() => {
    if (!isAuthenticated()) return;
    setAbrindoAgenda(true);
    void abrirSessao()
      .then(() => setStep('results'))
      .catch((err) => setLoginError(mensagemDeErro(err)))
      .finally(() => setAbrindoAgenda(false));
    // Só no mount: é a retomada, não uma reação a mudança de estado.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /*
    A agenda começa no topo, sempre.

    Ela nasce como esqueleto e só depois recebe a lista inteira, então
    qualquer posição de scroll anterior — a do reload, a de antes do
    "Atualizar", a de quando o aluno foi ao perfil — cairia no meio de um
    conteúdo que ainda não existia quando ele saiu. `scrollRestoration` já
    está em `manual` no `main.tsx`; aqui é a outra metade: assim que a busca
    termina e a lista aparece, o topo.
  */
  useEffect(() => {
    if (step !== 'results' || refreshing || abrindoAgenda) return;
    window.scrollTo(0, 0);
  }, [step, refreshing, abrindoAgenda]);

  /** Re-busca disciplinas e eventos. Pede login novamente se a sessão caiu. */
  const handleRefresh = async () => {
    if (!authenticated) {
      setStep('login');
      setLoginError('Faça login novamente para atualizar os dados.');
      return;
    }
    setRefreshError(null);
    setNovidades(null);
    setRefreshing(true);
    setSelectedSubjectId(null);
    try {
      await atualizarComparando({ subjects, events }, true);
    } catch (err) {
      console.error('Erro ao atualizar disciplinas:', err);
      setRefreshError(mensagemDeErro(err));
    } finally {
      setRefreshing(false);
    }
  };

  /** Limpa o estado local da sessão. */
  const resetLocalState = () => {
    setAuthenticated(false);
    setAccount(null);
    setProfile(null);
    setSubjects([]);
    setEvents([]);
    setNovidades(null);
    setSelectedSubjectId(null);
    setLoginError(null);
    setRefreshError(null);
    setSyncError(null);
    setStep('login');
  };

  /** Logout: encerra a sessão no backend e limpa o estado local. */
  const handleLogout = () => {
    void logout();
    resetLocalState();
  };

  /** Apaga o cache do aluno e volta pro login. */
  const handleClearCache = async () => {
    const confirmed = window.confirm(
      'Limpar seus dados salvos? As disciplinas e eventos serão apagados; o que você marcou como concluído é mantido. Você precisará fazer login novamente.',
    );
    if (!confirmed) return;
    try {
      await clearCache();
      handleLogout();
    } catch (err) {
      console.error('Erro ao limpar cache:', err);
      alert('Não foi possível limpar seus dados agora. Tente de novo em instantes.');
    }
  };

  /** Exclusão de conta — direito da LGPD, sem volta. */
  const handleDeleteAccount = async () => {
    const confirmed = window.confirm(
      'Excluir sua conta? Apagamos seus dados, suas marcações de concluído e as credenciais guardadas. Isso não pode ser desfeito.',
    );
    if (!confirmed) return;
    try {
      await deleteAccount();
      resetLocalState();
      setLoginError('Conta excluída. Seus dados foram apagados.');
    } catch (err) {
      console.error('Erro ao excluir conta:', err);
      alert('Não foi possível excluir a conta agora. Tente de novo em instantes.');
    }
  };

  /** Sincroniza todos os eventos não sincronizados de uma única disciplina */
  const handleSyncSubject = async (subjectName: string) => {
    const eventsToSync = events.filter((e) => !e.synced && e.subject === subjectName);
    if (eventsToSync.length === 0) return;

    setSyncing(true);
    setSyncError(null);
    try {
      const googleToken = await requestGoogleAccessToken();
      await syncToCalendar(eventsToSync, googleToken);
      setEvents((prev) =>
        prev.map((e) =>
          eventsToSync.some((se) => se.id === e.id) ? { ...e, synced: true } : e,
        ),
      );
    } catch (err) {
      console.error('Erro ao sincronizar:', err);
      setSyncError(mensagemDeErro(err));
    } finally {
      setSyncing(false);
    }
  };

  /** Devolve o link direto da atividade no Moodle. */
  const handleOpenPortal = async (
    subjectName: string,
    targetUrl?: string,
  ): Promise<string | null> => {
    if (!authenticated) {
      alert('Faça login novamente para abrir o Moodle.');
      return null;
    }
    try {
      return await openCourse(subjectName, targetUrl);
    } catch (err) {
      console.error('Erro ao obter link do Moodle:', err);
      alert('Não foi possível abrir o Moodle. Tente novamente.');
      return null;
    }
  };

  /*
    O esqueleto substitui a agenda só quando não existe agenda: primeiro
    acesso, ou cache apagado. Havendo lista na tela, ela fica — a busca por
    baixo se anuncia no botão "Atualizar", que gira.
  */
  const mostrandoEsqueleto = refreshing && subjects.length === 0;

  const selectedSubject = subjects.find((s) => s.id === selectedSubjectId) ?? null;
  const eventsForSelected = selectedSubject
    ? events.filter((e) => e.subject === selectedSubject.name)
    : [];

  // A tela de entrada já mostra a marca no meio dela; repetir a barra em cima
  // só empilharia dois logotipos e daria ar de chrome de sistema.
  const naTelaDeEntrada = step === 'login' && !abrindoAgenda;

  return (
    <div className="app">
      {!naTelaDeEntrada && (
        <AppHeader
          /* Durante o carregamento a barra fica só com a marca: Atualizar e o
             menu da conta agiriam sobre uma agenda que ainda não existe. */
          authenticated={authenticated && !abrindoAgenda}
          username={account?.username}
          fullName={profile?.moodle?.fullname}
          avatar={profile?.moodle?.avatar}
          onRefresh={handleRefresh}
          refreshing={refreshing || atualizandoAoFundo}
          onOpenProfile={() => setStep('profile')}
          onClearCache={handleClearCache}
          onLogout={handleLogout}
          onDeleteAccount={handleDeleteAccount}
        />
      )}

      {backendOffline && (
        <div className="backend-offline-banner" role="alert">
          <Icon name="sem-conexao" />
          Sem conexão com o servidor. Verifique sua internet e tente de novo em instantes.
        </div>
      )}

      {/*
        O erro de atualização subiu para cá junto com o botão Atualizar: quem
        dispara a ação no topo precisa ver a falha dela no topo, não enterrada
        no meio da lista de disciplinas.
      */}
      {refreshError && (
        <div className="app-banner error-banner" role="alert">
          <Icon name="alerta" />
          {refreshError}
        </div>
      )}

      {/*
        A tela de entrada ocupa a largura toda: ela é uma faixa escura ao lado
        do formulário, e a margem de 1100px do resto do app cortaria as duas.
      */}
      <main className={naTelaDeEntrada ? 'app-main app-main--auth' : 'app-main'}>
        {step === 'login' && !abrindoAgenda && (
          <>
            {/* A tela de entrada não tem barra — o botão do tema vem solto no
                canto, para quem abre o app à noite não precisar entrar antes
                de baixar o brilho. */}
            <ThemeToggle className="theme-toggle--solto" />
            <LoginForm onSubmit={handleLogin} loading={loginLoading} error={loginError} />
          </>
        )}

        {step === 'login' && abrindoAgenda && (
          <LoadingSkeleton message="Na primeira vez isso leva cerca de um minuto, porque estamos lendo todas as suas disciplinas." />
        )}

        {step === 'results' && naRotaAdmin && (
          <AdminPage onBack={() => navigate('/')} />
        )}

        {step === 'results' && !naRotaAdmin && activityKey && (
          <ActivityPage
            stableKey={activityKey}
            onBack={() => navigate('/')}
            onOpenPortal={handleOpenPortal}
          />
        )}

        {/*
          O esqueleto é para quando não há agenda nenhuma para mostrar — o
          primeiro acesso. Com uma lista na tela, atualizar não a apaga: ela
          fica, o botão "Atualizar" gira, e o que mudar é anunciado. Trocar a
          lista pelo esqueleto a cada busca era esconder do aluno justamente o
          que ele abriu o app para ver.
        */}
        {step === 'results' && !naRotaAdmin && !activityKey && !selectedSubject && mostrandoEsqueleto && (
          <LoadingSkeleton cards={Math.max(subjects.length, 3)} />
        )}

        {/*
          O convite das notificações abre a agenda enquanto o aluno não
          decidir. Volta a cada sessão de propósito — quem quiser encerrar o
          assunto tem o "Não mostre isso novamente" ali mesmo, sem precisar
          caçar configuração.
        */}
        {step === 'results' && !naRotaAdmin && !activityKey && !selectedSubject && (
          <AvisoNovidades frase={novidades} onFechar={() => setNovidades(null)} />
        )}

        {step === 'results' && !naRotaAdmin && !activityKey && !selectedSubject && !mostrandoEsqueleto && (
          <ConviteNotificacoes username={account?.username} />
        )}

        {step === 'results' && !naRotaAdmin && !activityKey && !selectedSubject && !mostrandoEsqueleto && (
          <SubjectList
            subjects={subjects}
            events={events}
            onSelectSubject={setSelectedSubjectId}
            lastScrapedAt={lastScrapedAt}
            onOpenEvent={abrirAtividade}
          />
        )}

        {step === 'results' && !naRotaAdmin && !activityKey && selectedSubject && (
          <SubjectDetail
            subject={selectedSubject}
            events={eventsForSelected}
            onBack={() => {
              setSelectedSubjectId(null);
              setSyncError(null);
            }}
            onSync={
              calendarEnabled ? () => handleSyncSubject(selectedSubject.name) : undefined
            }
            syncing={syncing}
            error={syncError}
            onOpenEvent={abrirAtividade}
          />
        )}

        {step === 'profile' && (
          <ProfilePage
            onBack={() => setStep('results')}
            onAbrirPainel={
              account?.isAdmin
                ? () => {
                    setStep('results');
                    navigate(ROTA_ADMIN);
                  }
                : undefined
            }
          />
        )}

        {step === 'assistant' && account && (
          <Assistant
            onBack={() => setStep('results')}
            username={account.username}
            used={account.assistantUsed}
            limit={account.assistantLimit}
            onQuotaChange={(used, limit) =>
              setAccount((prev) =>
                prev ? { ...prev, assistantUsed: used, assistantLimit: limit } : prev,
              )
            }
          />
        )}
      </main>

      {/*
        Lumi fica alcançável de qualquer tela — menos da sua própria, onde o
        botão só cobriria a conversa. Depende do assistente estar ligado no
        servidor: sem chave de IA, o backend recusa e o botão seria uma porta
        para lugar nenhum.
      */}
      {authenticated &&
        !abrindoAgenda &&
        step !== 'assistant' &&
        account?.assistantAvailable && (
          <AssistantFab
            onClick={() => setStep('assistant')}
            restantes={Math.max(0, account.assistantLimit - account.assistantUsed)}
          />
        )}

      {/*
        A autoria fica no rodapé, em duas linhas: primeiro quem fez, depois o
        aviso de que não é serviço oficial. Assinar o trabalho e deixar claro
        que ele não é da instituição são a mesma frase vista de dois lados, e
        quem chega pelo link de um colega merece as duas.
      */}
      <footer className="app-footer">
        <p className="app-footer__credit">
          Feito por{' '}
          <a href="https://github.com/JaimeLHF" target="_blank" rel="noreferrer">
            Jaime Luiz Hansen Filho
          </a>{' '}
          — Análise e Desenvolvimento de Sistemas, UNOESC São Miguel do Oeste
        </p>
        <p className="app-footer__legal">
          <span>Projeto independente de alunos — não é um serviço oficial da UNOESC.</span>
          <a href="/privacidade.html" target="_blank" rel="noreferrer">
            Privacidade e termos
          </a>
        </p>
      </footer>
    </div>
  );
};

/**
 * Mensagem de erro em português para o aluno. O backend manda o motivo em
 * `detail`; o `message` do axios ("Request failed with status code 401") não
 * diz nada para quem não é programador.
 */
function mensagemDeErro(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  if (detail) return detail;
  if (err instanceof Error && err.message) return err.message;
  return 'Ocorreu um erro inesperado. Tente novamente.';
}

export default App;
