import React, { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import { askAssistant } from '../services/api';
import type { AssistantMessage } from '../services/api';

interface AssistantProps {
  onBack: () => void;
  used: number;
  limit: number;
  onQuotaChange: (used: number, limit: number) => void;
}

/** Perguntas prontas — a maioria dos alunos não sabe o que pedir a uma IA. */
const SUGESTOES = [
  'O que eu preciso entregar nesta semana?',
  'Monte um plano de estudo até a minha próxima prova.',
  'Tem algum dia com entregas acumuladas?',
  'Por onde eu começo hoje?',
];

const Assistant: React.FC<AssistantProps> = ({ onBack, used, limit, onQuotaChange }) => {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fimDaConversa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimDaConversa.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const enviar = async (texto: string) => {
    const pergunta = texto.trim();
    if (!pergunta || loading) return;

    const historico: AssistantMessage[] = [...messages, { role: 'user', content: pergunta }];
    setMessages(historico);
    setInput('');
    setError(null);
    setLoading(true);

    try {
      const reply = await askAssistant(historico);
      setMessages([...historico, { role: 'assistant', content: reply.response }]);
      onQuotaChange(reply.used, reply.limit);
    } catch (err: unknown) {
      // A cota estourada volta como 429 com a mensagem pronta do backend.
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? 'Não consegui responder agora. Tente de novo em instantes.');
      setMessages(messages);
    } finally {
      setLoading(false);
    }
  };

  const restantes = Math.max(0, limit - used);

  return (
    <section className="assistant">
      <div className="assistant__header">
        <button type="button" className="btn-back" onClick={onBack}>
          <Icon name="voltar" />
          Voltar
        </button>
        <div>
          <h2 className="section-title">Lumi</h2>
          <p className="section-subtitle">
            Enxerga suas atividades pendentes — título, data e disciplina — e ajuda a
            planejar. Não tem acesso ao conteúdo das atividades.
          </p>
        </div>
        <span className="assistant__quota">
          {restantes} de {limit} perguntas neste mês
        </span>
      </div>

      <div className="assistant__chat">
        {messages.length === 0 && (
          <div className="assistant__suggestions">
            {SUGESTOES.map((s) => (
              <button
                key={s}
                type="button"
                className="assistant__suggestion"
                onClick={() => enviar(s)}
                disabled={restantes === 0}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`assistant__msg assistant__msg--${m.role === 'user' ? 'user' : 'bot'}`}
          >
            {m.content.split('\n').map((linha, j) => (
              <p key={j}>{linha}</p>
            ))}
          </div>
        ))}

        {loading && (
          <div className="assistant__msg assistant__msg--bot">
            <span className="spinner spinner--dark" aria-hidden="true" /> Pensando…
          </div>
        )}

        <div ref={fimDaConversa} />
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <Icon name="alerta" />
          {error}
        </div>
      )}

      <form
        className="assistant__form"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar(input);
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            restantes === 0
              ? 'Você usou todas as perguntas deste mês'
              : 'Pergunte à Lumi sobre prazos, prioridades, plano de estudo…'
          }
          disabled={loading || restantes === 0}
        />
        <button
          type="submit"
          className="btn-primary"
          disabled={loading || restantes === 0 || !input.trim()}
        >
          Enviar
        </button>
      </form>
    </section>
  );
};

export default Assistant;
