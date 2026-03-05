import React, { useState } from 'react';
import LoginForm from './components/LoginForm';
import SubjectList from './components/SubjectList';
import EventList from './components/EventList';
import { scrapePortal, parseEvents, syncToCalendar } from './services/api';
import type { Subject, AcademicEvent, LoginCredentials } from './types';
import './index.css';

/** Etapas do fluxo principal da aplicação */
type AppStep = 'login' | 'loading' | 'results';

const App: React.FC = () => {
  // Controle de etapa atual
  const [step, setStep] = useState<AppStep>('login');

  // Dados de domínio
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [events, setEvents] = useState<AcademicEvent[]>([]);
  const [selectedSubjectIds, setSelectedSubjectIds] = useState<Set<string>>(new Set());

  // Estados de UI
  const [loadingMessage, setLoadingMessage] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  // ----------------------------------------------------------------
  // Handlers de fluxo
  // ----------------------------------------------------------------

  /** Inicia o processo de busca após o aluno preencher o login */
  const handleLogin = async (credentials: LoginCredentials) => {
    setLoginError(null);
    setStep('loading');
    setLoadingMessage('Acessando o portal UNOESC…');

    try {
      // Passo 1: Faz login e extrai conteúdo das disciplinas
      const scrapeResult = await scrapePortal(credentials);
      setSubjects(scrapeResult.subjects);
      setSelectedSubjectIds(new Set(scrapeResult.subjects.map((s) => s.id)));

      setLoadingMessage('Identificando eventos com IA…');

      // Passo 2: Usa o Gemini para extrair eventos estruturados
      const extractedEvents = await parseEvents(scrapeResult.subjects);
      setEvents(extractedEvents);

      setStep('results');
    } catch (err: unknown) {
      // Retorna ao login com a mensagem de erro
      setStep('login');
      if (err instanceof Error) {
        setLoginError(err.message);
      } else {
        setLoginError('Ocorreu um erro inesperado. Tente novamente.');
      }
    }
  };

  /** Alterna a seleção de uma disciplina */
  const handleToggleSubject = (id: string) => {
    setSelectedSubjectIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  /** Sincroniza os eventos das disciplinas selecionadas com o Google Calendar */
  const handleSync = async () => {
    const eventsToSync = events.filter(
      (e) =>
        !e.synced &&
        subjects
          .filter((s) => selectedSubjectIds.has(s.id))
          .map((s) => s.name)
          .includes(e.subject)
    );

    if (eventsToSync.length === 0) return;

    setSyncing(true);
    try {
      await syncToCalendar(eventsToSync);
      // Marca os eventos como sincronizados na interface
      setEvents((prev) =>
        prev.map((e) =>
          eventsToSync.some((se) => se.id === e.id) ? { ...e, synced: true } : e
        )
      );
    } catch (err) {
      console.error('Erro ao sincronizar com o Google Calendar:', err);
    } finally {
      setSyncing(false);
    }
  };

  /** Eventos filtrados pelas disciplinas selecionadas */
  const filteredEvents = events.filter((e) =>
    subjects
      .filter((s) => selectedSubjectIds.has(s.id))
      .map((s) => s.name)
      .includes(e.subject)
  );

  // ----------------------------------------------------------------
  // Renderização
  // ----------------------------------------------------------------

  return (
    <div className="app">
      {/* Cabeçalho */}
      <header className="app-header">
        <h1 className="app-title">📚 Agenda UNOESC</h1>
        <p className="app-subtitle">
          Encontre suas atividades acadêmicas e sincronize com o Google Calendar
        </p>
      </header>

      <main className="app-main">
        {/* Etapa 1: Login */}
        {step === 'login' && (
          <LoginForm
            onSubmit={handleLogin}
            loading={false}
            error={loginError}
          />
        )}

        {/* Etapa 2: Carregamento */}
        {step === 'loading' && (
          <div className="loading-screen">
            <div className="loading-spinner" aria-label="Carregando" />
            <p className="loading-message">{loadingMessage}</p>
          </div>
        )}

        {/* Etapa 3: Resultados */}
        {step === 'results' && (
          <div className="results-layout">
            <SubjectList
              subjects={subjects}
              events={events}
              selectedIds={selectedSubjectIds}
              onToggle={handleToggleSubject}
            />
            <EventList
              events={filteredEvents}
              onSync={handleSync}
              syncing={syncing}
            />
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
