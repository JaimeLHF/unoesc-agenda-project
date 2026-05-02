import React, { useState, useRef, useEffect } from 'react';
import type { AcademicEvent } from '../types';
import { fetchActivityContent, askAiHelp } from '../services/api';
import type { AiMessage } from '../services/api';

interface AiHelperProps {
  event: AcademicEvent;
  credentials: { username: string; password: string };
  onBack: () => void;
}

type LoadingState = 'idle' | 'loading-content' | 'sending';

const AiHelper: React.FC<AiHelperProps> = ({ event, credentials, onBack }) => {
  const [activityContent, setActivityContent] = useState<string>('');
  const [contentLoading, setContentLoading] = useState<LoadingState>('idle');
  const [contentError, setContentError] = useState<string | null>(null);
  const [messages, setMessages] = useState<AiMessage[]>([]);
  const [input, setInput] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showAnswerInput, setShowAnswerInput] = useState(false);
  const [answerUrl, setAnswerUrl] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Carrega o conteúdo da atividade ao montar
  useEffect(() => {
    if (!event.url) {
      setContentError('Esta atividade não possui link para o Moodle.');
      return;
    }
    setContentLoading('loading-content');
    fetchActivityContent(credentials.username, credentials.password, event.subject, event.url)
      .then((content) => {
        setActivityContent(content);
        setContentLoading('idle');
      })
      .catch((err) => {
        console.error('Erro ao carregar conteúdo:', err);
        setContentError('Não foi possível carregar o conteúdo da atividade.');
        setContentLoading('idle');
      });
  }, [event, credentials]);

  // Scroll pro final do chat quando novas mensagens chegam
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /** Remove mensagens contendo URLs do histórico enviado à IA — ela não acessa links e
   *  ao ver uma URL na conversa responde "não consigo acessar", confundindo a resposta. */
  const sanitizeForAi = (msgs: AiMessage[]): AiMessage[] =>
    msgs.filter((m) => !/https?:\/\//i.test(m.content));

  /** Extrai questões da URL da prova e pede respostas diretas. */
  const handleGetAnswers = async () => {
    const url = answerUrl.trim();
    if (!url || contentLoading === 'sending' || contentLoading === 'loading-content') return;

    setShowAnswerInput(false);
    setAnswerUrl('');

    const userMsg: AiMessage = { role: 'user', content: '📝 Buscar respostas da prova' };
    const updatedMessages = [...messages, userMsg];
    setMessages([
      ...updatedMessages,
      { role: 'assistant', content: '⏳ Acessando a prova e extraindo questões…' },
    ]);

    setContentLoading('loading-content');
    try {
      const content = await fetchActivityContent(
        credentials.username, credentials.password, event.subject, url
      );
      if (!content) {
        setMessages([
          ...updatedMessages,
          { role: 'assistant', content: 'Não consegui acessar a prova. Verifique se ela foi iniciada e se o link está correto.' },
        ]);
        setContentLoading('idle');
        return;
      }

      setActivityContent(content);
      setContentLoading('sending');

      const promptMsg: AiMessage = {
        role: 'user',
        content: `Responda SOMENTE neste formato Markdown exato, sem nenhum texto antes ou depois:\n\nRespostas da Prova ${event.title}:\n\n1) **x**,\n2) **x**,\n3) **x**,\n\n(continue para todas as questões)\n\nOnde x é a letra da alternativa correta (a, b, c, d ou e), em negrito. Nada mais — sem explicações, sem enunciados, sem texto extra. Se alguma questão for dissertativa, coloque a resposta em negrito em no máximo 1 linha curta.`,
      };
      const response = await askAiHelp(content, event.title, event.subject, [promptMsg]);
      setMessages([...updatedMessages, { role: 'assistant', content: response }]);
    } catch {
      setMessages([
        ...updatedMessages,
        { role: 'assistant', content: 'Erro ao buscar respostas. Tente novamente.' },
      ]);
    } finally {
      setContentLoading('idle');
    }
  };

  /** Detecta se o texto contém uma URL do Moodle (quiz attempt, mod, etc.) */
  const extractMoodleUrl = (text: string): string | null => {
    const match = text.match(/(https?:\/\/[^\s]+(?:mod\/quiz\/attempt|mod\/quiz\/view|mod\/assign|mod\/forum|course\/view)[^\s]*)/i);
    return match ? match[1] : null;
  };

  /** Extrai conteúdo de uma URL e atualiza o contexto da IA */
  const handleFetchUrl = async (url: string, updatedMessages: AiMessage[]) => {
    setContentLoading('loading-content');
    try {
      const content = await fetchActivityContent(
        credentials.username, credentials.password, event.subject, url
      );
      if (content) {
        setActivityContent(content);
        // Agora pede as respostas automaticamente com o novo conteúdo
        const prompt = 'Com base no conteúdo que acabei de carregar da prova, liste TODAS as perguntas com suas respectivas respostas corretas. Para cada questão, mostre: o número/enunciado, a resposta correta (letra se for múltipla escolha), e uma justificativa breve.';
        const aiMsg: AiMessage = { role: 'user', content: prompt };
        const finalMessages = [...updatedMessages, aiMsg];
        setMessages(finalMessages);
        setContentLoading('sending');

        const response = await askAiHelp(content, event.title, event.subject, sanitizeForAi(finalMessages));
        setMessages([...finalMessages, { role: 'assistant', content: response }]);
      } else {
        setMessages([
          ...updatedMessages,
          { role: 'assistant', content: 'Não consegui extrair o conteúdo dessa página. Verifique se o link está correto e se a prova foi iniciada.' },
        ]);
      }
    } catch {
      setMessages([
        ...updatedMessages,
        { role: 'assistant', content: 'Erro ao acessar a página. Verifique se você iniciou a prova e se o link está correto.' },
      ]);
    } finally {
      setContentLoading('idle');
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || contentLoading === 'sending' || contentLoading === 'loading-content') return;

    const userMsg: AiMessage = { role: 'user', content: text };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput('');

    // Detecta URL do Moodle — extrai conteúdo e responde automaticamente
    const moodleUrl = extractMoodleUrl(text);
    if (moodleUrl) {
      setMessages([
        ...updatedMessages,
        { role: 'assistant', content: '⏳ Acessando a página e extraindo as questões…' },
      ]);
      await handleFetchUrl(moodleUrl, updatedMessages);
      return;
    }

    setContentLoading('sending');
    try {
      const response = await askAiHelp(
        activityContent,
        event.title,
        event.subject,
        sanitizeForAi(updatedMessages),
      );
      setMessages([...updatedMessages, { role: 'assistant', content: response }]);
    } catch (err) {
      console.error('Erro ao consultar IA:', err);
      setMessages([
        ...updatedMessages,
        { role: 'assistant', content: 'Desculpe, ocorreu um erro. Tente novamente.' },
      ]);
    } finally {
      setContentLoading('idle');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Tela de loading inicial enquanto extrai conteúdo do Moodle
  if (contentLoading === 'loading-content' && messages.length === 0) {
    return (
      <div className="ai-helper">
        <div className="ai-helper__loading-screen">
          <div className="loading-spinner" />
          <p className="ai-helper__loading-hint">Carregando informações...</p>
          <button type="button" className="btn-back" onClick={onBack} style={{ marginTop: '1.5rem' }}>
            ← Voltar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-helper">
      {/* Header */}
      <header className="ai-helper__header">
        <button type="button" className="btn-back" onClick={onBack}>
          ← Voltar
        </button>
        <div className="ai-helper__header-info">
          <h2 className="ai-helper__title">{event.title}</h2>
          <span className="ai-helper__meta">
            {event.subject} · {event.date}{event.time ? ` às ${event.time}` : ''}
          </span>
        </div>
        <button
          type="button"
          className="btn-answers"
          onClick={() => setShowAnswerInput(!showAnswerInput)}
          disabled={contentLoading === 'sending' || contentLoading === 'loading-content'}
          title="Colar link da prova para obter respostas"
        >
          📝 Respostas
        </button>
        <button
          type="button"
          className="btn-toggle-sidebar"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          title={sidebarOpen ? 'Ocultar enunciado' : 'Mostrar enunciado'}
        >
          {sidebarOpen ? '◀ Ocultar' : '▶ Enunciado'}
        </button>
      </header>

      {showAnswerInput && (
        <div className="ai-helper__url-bar">
          <input
            type="text"
            className="ai-helper__url-input"
            value={answerUrl}
            onChange={(e) => setAnswerUrl(e.target.value)}
            placeholder="Cole o link da prova iniciada (ex: .../mod/quiz/attempt.php?attempt=123)"
            onKeyDown={(e) => { if (e.key === 'Enter') handleGetAnswers(); }}
            autoFocus
          />
          <button
            type="button"
            className="btn-send"
            onClick={handleGetAnswers}
            disabled={!answerUrl.trim()}
          >
            Buscar respostas
          </button>
        </div>
      )}

      <div className="ai-helper__body">
        {/* Sidebar com conteúdo da atividade */}
        {sidebarOpen && (
          <aside className="ai-helper__sidebar">
            <h3 className="ai-helper__sidebar-title">Conteúdo da atividade</h3>
            {contentLoading === 'loading-content' && (
              <div className="ai-helper__sidebar-loading">
                <div className="loading-spinner" />
                <p>Extraindo conteúdo do Moodle…</p>
              </div>
            )}
            {contentError && <p className="ai-helper__error">{contentError}</p>}
            {activityContent && (
              <pre className="ai-helper__content">{activityContent}</pre>
            )}
          </aside>
        )}

        {/* Chat */}
        <main className="ai-helper__chat">
          <div className="ai-helper__messages">
            {messages.length === 0 && contentLoading !== 'loading-content' && (
              <div className="ai-helper__empty">
                <p>Pergunte qualquer coisa sobre esta atividade.</p>
                <p className="ai-helper__empty-hint">
                  Cole o link da prova iniciada (ex: attempt.php?attempt=...) para extrair as questões automaticamente.
                </p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`ai-helper__bubble ai-helper__bubble--${msg.role}`}
              >
                <div className="ai-helper__bubble-content">
                  {msg.role === 'assistant' ? (
                    <div dangerouslySetInnerHTML={{ __html: formatMarkdown(msg.content) }} />
                  ) : (
                    <p>{msg.content}</p>
                  )}
                </div>
              </div>
            ))}
            {contentLoading === 'sending' && (
              <div className="ai-helper__bubble ai-helper__bubble--assistant">
                <div className="ai-helper__bubble-content">
                  <div className="ai-helper__typing">
                    <span /><span /><span />
                  </div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div className="ai-helper__input-area">
            <textarea
              className="ai-helper__input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Digite sua dúvida sobre a atividade…"
              disabled={contentLoading === 'sending' || contentLoading === 'loading-content'}
              rows={2}
            />
            <button
              type="button"
              className="btn-send"
              onClick={handleSend}
              disabled={!input.trim() || contentLoading === 'sending' || contentLoading === 'loading-content'}
            >
              Enviar
            </button>
          </div>
        </main>
      </div>
    </div>
  );
};

/** Converte markdown básico em HTML para as respostas da IA. */
function formatMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n/g, '<br/>');
}

export default AiHelper;
