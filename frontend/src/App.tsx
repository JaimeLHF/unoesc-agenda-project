import React, { useEffect, useState } from 'react';
import LoginForm from './components/LoginForm';
import SubjectList from './components/SubjectList';
import SubjectDetail from './components/SubjectDetail';
import AiHelper from './components/AiHelper';
import {
  login,
  logout,
  scrapePortal,
  syncToCalendar,
  fetchCache,
  clearCache,
  openCourse,
} from './services/api';
import { requestGoogleAccessToken } from './services/googleAuth';
import { useDoneEvents } from './contexts/DoneEventsContext';
import type { Subject, AcademicEvent, LoginCredentials } from './types';
import './index.css';

type AppStep = 'login' | 'results' | 'ai-helper';

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

  const [aiHelperEvent, setAiHelperEvent] = useState<AcademicEvent | null>(null);

  const [loadingMessage, setLoadingMessage] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [backendOffline, setBackendOffline] = useState(false);

  const { hydrate } = useDoneEvents();

  // Banner de "backend offline": axios interceptor dispatcha eventos
  // 'backend-online'/'backend-offline' a cada request.
  useEffect(() => {
    const onOnline = () => setBackendOffline(false);
    const onOffline = () => setBackendOffline(true);
    // O backend respondeu 401: o token caiu (expirou, ou o backend reiniciou).
    // Volta pro login em vez de deixar a tela travada em erro.
    const onSessionExpired = () => {
      setAuthenticated(false);
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

  /** Boot — tenta carregar cache do backend; se vazio, fica na tela de login. */
  useEffect(() => {
    let cancelled = false;
    fetchCache()
      .then((cache) => {
        if (cancelled) return;
        hydrate(cache.doneKeys);
        if (cache.subjects.length > 0 || cache.events.length > 0) {
          setSubjects(cache.subjects);
          setEvents(cache.events);
          setLastScrapedAt(cache.lastScrapedAt);
          setStep('results');
        }
      })
      .catch((err) => console.warn('Cache indisponível, indo pro login:', err));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Busca disciplinas e eventos. Usado no login e no refresh. */
  const fetchAll = async () => {
    setLoadingMessage('Consultando o Moodle…');
    const scrapeResult = await scrapePortal();

    setSubjects(scrapeResult.subjects);
    setEvents(scrapeResult.calendar_events);
    setLastScrapedAt(new Date().toISOString());
  };

  /** Login inicial — captura credenciais e busca dados. */
  const [loginLoading, setLoginLoading] = useState(false);

  const handleLogin = async (creds: LoginCredentials) => {
    setLoginError(null);
    setLoginLoading(true);

    try {
      await login(creds);
      setAuthenticated(true);
      await fetchAll();
      setLoginLoading(false);
      setStep('results');
    } catch (err: unknown) {
      setLoginLoading(false);
      setLoginError(
        err instanceof Error ? err.message : 'Ocorreu um erro inesperado. Tente novamente.',
      );
    }
  };

  /** Re-busca disciplinas e eventos. Pede login novamente se não tiver credenciais. */
  const handleRefresh = async () => {
    if (!authenticated) {
      // Veio do cache — precisa logar de novo pra fazer scraping
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
      setRefreshError(err instanceof Error ? err.message : 'Falha ao atualizar.');
    } finally {
      setRefreshing(false);
    }
  };

  /** Logout: encerra a sessão no backend e limpa o estado local. */
  const handleLogout = () => {
    void logout();
    setAuthenticated(false);
    setSubjects([]);
    setEvents([]);
    setSelectedSubjectId(null);
    setLoginError(null);
    setRefreshError(null);
    setSyncError(null);
    setStep('login');
  };

  /** Apaga o cache local (no banco) e volta pro login. Útil pra debugar. */
  const handleClearCache = async () => {
    const confirmed = window.confirm(
      'Limpar o cache local? Subjects e eventos serão apagados; eventos marcados como concluídos serão mantidos. Você precisará fazer login novamente.',
    );
    if (!confirmed) return;
    try {
      await clearCache();
      handleLogout();
    } catch (err) {
      console.error('Erro ao limpar cache:', err);
      alert('Falha ao limpar o cache. Verifique se o backend está rodando.');
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
      setSyncError(err instanceof Error ? err.message : 'Falha ao sincronizar.');
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

  /** Abre a tela de assistente IA para uma atividade. */
  const handleAskAi = (event: AcademicEvent) => {
    if (!authenticated) {
      alert('Faça login novamente para usar o assistente de IA.');
      return;
    }
    setAiHelperEvent(event);
    setStep('ai-helper');
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
          Encontre suas atividades acadêmicas e sincronize com o Google Calendar
        </p>
      </header>

      {backendOffline && (
        <div className="backend-offline-banner" role="alert">
          ⚠️ Sem conexão com o servidor. Confira se o backend (uvicorn) está rodando em
          {' '}<code>http://localhost:8880</code>.
        </div>
      )}

      <main className="app-main">
        {step === 'login' && (
          <LoginForm onSubmit={handleLogin} loading={loginLoading} error={loginError} />
        )}

        {step === 'login' && loginLoading && (
          <div className="loading-screen">
            <div className="loading-spinner" aria-label="Carregando" />
            <p className="loading-message">{loadingMessage}</p>
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
            lastScrapedAt={lastScrapedAt}
            onOpenPortal={handleOpenPortal}
            onAskAi={handleAskAi}
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
            onSync={() => handleSyncSubject(selectedSubject.name)}
            syncing={syncing}
            error={syncError}
            onOpenPortal={handleOpenPortal}
            onAskAi={handleAskAi}
          />
        )}

        {step === 'ai-helper' && aiHelperEvent && authenticated && (
          <AiHelper
            event={aiHelperEvent}
            onBack={() => {
              setAiHelperEvent(null);
              setStep('results');
            }}
          />
        )}
      </main>
    </div>
  );
};

export default App;
