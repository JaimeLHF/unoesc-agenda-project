import React, { useEffect, useState } from 'react';
import LoginForm from './components/LoginForm';
import SubjectList from './components/SubjectList';
import SubjectDetail from './components/SubjectDetail';
import Assistant from './components/Assistant';
import {
  login,
  logout,
  scrapePortal,
  syncToCalendar,
  fetchCache,
  fetchAccount,
  deleteAccount,
  clearCache,
  openCourse,
} from './services/api';
import type { Account } from './services/api';
import { requestGoogleAccessToken } from './services/googleAuth';
import { useDoneEvents } from './contexts/DoneEventsContext';
import type { Subject, AcademicEvent, LoginCredentials } from './types';
import './index.css';

type AppStep = 'login' | 'results' | 'assistant';

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

  const [loadingMessage, setLoadingMessage] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [backendOffline, setBackendOffline] = useState(false);

  const { hydrate } = useDoneEvents();

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

  /** Busca disciplinas e eventos no Moodle. Usado no login e no refresh. */
  const fetchAll = async () => {
    setLoadingMessage('Consultando o Moodle…');
    const scrapeResult = await scrapePortal();

    setSubjects(scrapeResult.subjects);
    setEvents(scrapeResult.calendar_events);
    setLastScrapedAt(new Date().toISOString());
  };

  /** Login inicial — autentica, mostra o que já existe e atualiza. */
  const [loginLoading, setLoginLoading] = useState(false);

  const handleLogin = async (creds: LoginCredentials) => {
    setLoginError(null);
    setLoginLoading(true);
    setLoadingMessage('Entrando…');

    try {
      await login(creds);
      setAuthenticated(true);
      void fetchAccount().then(setAccount).catch(() => setAccount(null));

      // Se o aluno já usou o app antes, o cache abre a tela na hora e o
      // Moodle é consultado em seguida. No primeiro acesso não há cache, e aí
      // a espera pelo scrape é inevitável.
      setLoadingMessage('Carregando sua agenda…');
      const cache = await fetchCache().catch(() => null);
      const temCache = Boolean(cache && (cache.subjects.length > 0 || cache.events.length > 0));

      if (cache) hydrate(cache.doneKeys);
      if (cache && temCache) {
        setSubjects(cache.subjects);
        setEvents(cache.events);
        setLastScrapedAt(cache.lastScrapedAt);
        setStep('results');
        setLoginLoading(false);
        // Atualiza em segundo plano — a tela já está utilizável.
        setRefreshing(true);
        fetchAll()
          .catch((err) => console.warn('Falha ao atualizar em segundo plano:', err))
          .finally(() => setRefreshing(false));
        return;
      }

      await fetchAll();
      setLoginLoading(false);
      setStep('results');
    } catch (err: unknown) {
      setLoginLoading(false);
      setLoginError(mensagemDeErro(err));
    }
  };

  /** Re-busca disciplinas e eventos. Pede login novamente se a sessão caiu. */
  const handleRefresh = async () => {
    if (!authenticated) {
      setStep('login');
      setLoginError('Faça login novamente para atualizar os dados.');
      return;
    }
    setRefreshError(null);
    setRefreshing(true);
    setSelectedSubjectId(null);
    try {
      await fetchAll();
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
    setSubjects([]);
    setEvents([]);
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

  const selectedSubject = subjects.find((s) => s.id === selectedSubjectId) ?? null;
  const eventsForSelected = selectedSubject
    ? events.filter((e) => e.subject === selectedSubject.name)
    : [];

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">📚 Agenda UNOESC</h1>
        <p className="app-subtitle">
          Todas as suas entregas, provas e webconferências numa lista só
        </p>
      </header>

      {backendOffline && (
        <div className="backend-offline-banner" role="alert">
          ⚠️ Sem conexão com o servidor. Verifique sua internet e tente de novo em instantes.
        </div>
      )}

      <main className="app-main">
        {step === 'login' && !loginLoading && (
          <LoginForm onSubmit={handleLogin} loading={loginLoading} error={loginError} />
        )}

        {step === 'login' && loginLoading && (
          <div className="loading-screen">
            <div className="loading-spinner" aria-label="Carregando" />
            <p className="loading-message">{loadingMessage}</p>
            <p className="loading-hint">
              Na primeira vez isso leva cerca de um minuto — estamos lendo todas as suas
              disciplinas.
            </p>
          </div>
        )}

        {step === 'results' && !selectedSubject && (
          <SubjectList
            subjects={subjects}
            events={events}
            onSelectSubject={setSelectedSubjectId}
            onRefresh={handleRefresh}
            refreshing={refreshing}
            refreshError={refreshError}
            onLogout={handleLogout}
            onClearCache={handleClearCache}
            onDeleteAccount={handleDeleteAccount}
            lastScrapedAt={lastScrapedAt}
            onOpenPortal={handleOpenPortal}
            onOpenAssistant={() => setStep('assistant')}
            assistantAvailable={account?.assistantAvailable ?? false}
          />
        )}

        {step === 'results' && selectedSubject && (
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
            onOpenPortal={handleOpenPortal}
          />
        )}

        {step === 'assistant' && account && (
          <Assistant
            onBack={() => setStep('results')}
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

      <footer className="app-footer">
        <span>
          Projeto independente de alunos — não é um serviço oficial da UNOESC.
        </span>
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
