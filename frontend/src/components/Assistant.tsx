import React, { useEffect, useMemo, useRef, useState } from 'react';
import Icon from './Icon';
import { askAssistant } from '../services/api';
import type { AssistantMessage } from '../services/api';
import {
  apagarTudo,
  carregar,
  novoId,
  salvar,
  tituloDaPergunta,
} from '../lib/lumiConversas';
import type { LumiConversa } from '../lib/lumiConversas';

interface AssistantProps {
  onBack: () => void;
  used: number;
  limit: number;
  onQuotaChange: (used: number, limit: number) => void;
  /** Matrícula: as conversas ficam no navegador, separadas por conta. */
  username: string;
}

/** Perguntas prontas — a maioria dos alunos não sabe o que pedir a uma IA. */
const SUGESTOES = [
  'O que eu preciso entregar nesta semana?',
  'Monte um plano de estudo até a minha próxima prova.',
  'Tem algum dia com entregas acumuladas?',
  'Por onde eu começo hoje?',
];

/**
 * A tela da Lumi: conversas à esquerda, conversa aberta à direita.
 *
 * Antes era uma tela só, e cada visita começava do zero — sair para ver a
 * agenda apagava a resposta que motivou a saída. A lista lateral guarda o que
 * já foi perguntado (no navegador, ver `lib/lumiConversas`) e dá lugar às
 * ações que não cabiam em canto nenhum: começar de novo e apagar tudo.
 *
 * No celular a lista vira uma gaveta: a conversa ocupa a tela inteira, e o
 * histórico entra por cima quando pedido.
 */
const Assistant: React.FC<AssistantProps> = ({
  onBack,
  used,
  limit,
  onQuotaChange,
  username,
}) => {
  const [conversas, setConversas] = useState<LumiConversa[]>(() => carregar(username));
  const [ativaId, setAtivaId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gavetaAberta, setGavetaAberta] = useState(false);
  const fimDaConversa = useRef<HTMLDivElement>(null);

  const ativa = useMemo(
    () => conversas.find((c) => c.id === ativaId) ?? null,
    [conversas, ativaId],
  );
  const mensagens = ativa?.mensagens ?? [];
  const restantes = Math.max(0, limit - used);

  useEffect(() => {
    fimDaConversa.current?.scrollIntoView({ behavior: 'smooth' });
  }, [mensagens.length, loading]);

  const persistir = (proximas: LumiConversa[]) => {
    setConversas(proximas);
    salvar(username, proximas);
  };

  const abrir = (id: string) => {
    setAtivaId(id);
    setError(null);
    setGavetaAberta(false);
  };

  const comecarNova = () => {
    setAtivaId(null);
    setInput('');
    setError(null);
    setGavetaAberta(false);
  };

  const apagarConversa = (id: string) => {
    persistir(conversas.filter((c) => c.id !== id));
    if (id === ativaId) setAtivaId(null);
  };

  const limparHistorico = () => {
    apagarTudo(username);
    setConversas([]);
    setAtivaId(null);
  };

  const enviar = async (texto: string) => {
    const pergunta = texto.trim();
    if (!pergunta || loading) return;

    // Sem conversa aberta, a pergunta inaugura uma — e dá nome a ela.
    const alvo: LumiConversa = ativa ?? {
      id: novoId(),
      titulo: tituloDaPergunta(pergunta),
      criadaEm: Date.now(),
      mensagens: [],
    };
    const historico: AssistantMessage[] = [
      ...alvo.mensagens,
      { role: 'user', content: pergunta },
    ];

    const comPergunta: LumiConversa = { ...alvo, mensagens: historico };
    const outras = conversas.filter((c) => c.id !== alvo.id);
    persistir([comPergunta, ...outras]);
    setAtivaId(alvo.id);
    setInput('');
    setError(null);
    setLoading(true);

    try {
      const reply = await askAssistant(historico);
      persistir([
        { ...alvo, mensagens: [...historico, { role: 'assistant', content: reply.response }] },
        ...outras,
      ]);
      onQuotaChange(reply.used, reply.limit);
    } catch (err: unknown) {
      // A cota estourada volta como 429 com a mensagem pronta do backend.
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? 'Não consegui responder agora. Tente de novo em instantes.');
      // A pergunta sem resposta sai da conversa: deixá-la ali daria a impressão
      // de que a Lumi leu e ignorou.
      persistir(alvo.mensagens.length ? [alvo, ...outras] : outras);
      if (!alvo.mensagens.length) setAtivaId(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className={`lumi${gavetaAberta ? ' lumi--gaveta-aberta' : ''}`}>
      <aside className="lumi__lateral">
        <button type="button" className="lumi__nova" onClick={comecarNova}>
          <Icon name="mais" size={1} />
          Nova conversa
        </button>

        <div className="lumi__historico">
          <p className="lumi__historico-titulo">Conversas</p>
          {conversas.length === 0 ? (
            <p className="lumi__historico-vazio">
              Suas conversas ficam aqui, neste navegador.
            </p>
          ) : (
            <ul>
              {conversas.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={`lumi__conversa${c.id === ativaId ? ' lumi__conversa--ativa' : ''}`}
                    onClick={() => abrir(c.id)}
                  >
                    <Icon name="conversa" size={0.9} />
                    <span className="lumi__conversa-titulo">{c.titulo}</span>
                  </button>
                  <button
                    type="button"
                    className="lumi__conversa-apagar"
                    onClick={() => apagarConversa(c.id)}
                    aria-label={`Apagar a conversa “${c.titulo}”`}
                    title="Apagar esta conversa"
                  >
                    <Icon name="fechar" size={0.8} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="lumi__acoes">
          <p className="lumi__cota">
            <strong>{restantes}</strong> de {limit} perguntas neste mês
          </p>
          {conversas.length > 0 && (
            <button type="button" className="lumi__limpar" onClick={limparHistorico}>
              <Icon name="lixeira" size={0.9} />
              Apagar todas as conversas
            </button>
          )}
          <button type="button" className="lumi__voltar" onClick={onBack}>
            <Icon name="voltar" size={0.9} />
            Voltar para a agenda
          </button>
        </div>
      </aside>

      {/* Fundo escuro atrás da gaveta no celular: fechar tocando fora é o
          gesto que todo mundo tenta primeiro. */}
      {gavetaAberta && (
        <button
          type="button"
          className="lumi__cortina"
          onClick={() => setGavetaAberta(false)}
          aria-label="Fechar a lista de conversas"
        />
      )}

      <div className="lumi__principal">
        <header className="lumi__topo">
          <button
            type="button"
            className="lumi__menu"
            onClick={() => setGavetaAberta(true)}
            aria-label="Abrir a lista de conversas"
          >
            <Icon name="menu" size={1.1} />
          </button>
          <span className="lumi__marca" aria-hidden="true">
            <Icon name="ia" size={1.2} />
          </span>
          <div>
            <h2 className="lumi__nome">Lumi</h2>
            <p className="lumi__descricao">
              Enxerga suas atividades pendentes — título, data e disciplina. Não tem
              acesso ao conteúdo delas.
            </p>
          </div>
        </header>

        <div className="lumi__chat">
          {mensagens.length === 0 && (
            <div className="lumi__abertura">
              <span className="lumi__abertura-icone" aria-hidden="true">
                <Icon name="ia" size={2} />
              </span>
              <p className="lumi__abertura-texto">
                Pergunte o que fazer primeiro, como dividir o tempo até um prazo ou onde
                as entregas se acumularam.
              </p>
              <div className="lumi__sugestoes">
                {SUGESTOES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="lumi__sugestao"
                    onClick={() => enviar(s)}
                    disabled={restantes === 0}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {mensagens.map((m, i) => (
            <div key={i} className={`lumi__msg lumi__msg--${m.role === 'user' ? 'aluno' : 'lumi'}`}>
              {m.role === 'assistant' && (
                <span className="lumi__msg-icone" aria-hidden="true">
                  <Icon name="ia" size={0.95} />
                </span>
              )}
              <div className="lumi__msg-balao">
                {m.content.split('\n').map((linha, j) => (
                  <p key={j}>{linha}</p>
                ))}
              </div>
            </div>
          ))}

          {loading && (
            <div className="lumi__msg lumi__msg--lumi">
              <span className="lumi__msg-icone" aria-hidden="true">
                <Icon name="ia" size={0.95} />
              </span>
              <div className="lumi__msg-balao lumi__msg-balao--pensando">
                <span className="spinner spinner--dark" aria-hidden="true" /> Pensando…
              </div>
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
          className="lumi__form"
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
      </div>
    </section>
  );
};

export default Assistant;
