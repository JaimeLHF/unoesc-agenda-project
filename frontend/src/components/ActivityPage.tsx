import React, { useEffect, useState } from 'react';
import Icon from './Icon';
import { fetchActivity } from '../services/api';
import type { ActivityDetail } from '../services/api';
import { useDoneEvents } from '../contexts/DoneEventsContext';
import type { AcademicEvent, EventType } from '../types';

interface ActivityPageProps {
  stableKey: string;
  onBack: () => void;
  onOpenPortal?: (subjectName: string, targetUrl?: string) => Promise<string | null>;
}

const TYPE_LABELS: Record<EventType, string> = {
  webconference: 'Webconferência',
  deadline: 'Entrega',
  exam: 'Prova',
  other: 'Evento',
};

function formatFullDate(iso: string, time?: string | null): string {
  try {
    const d = new Date(`${iso}T${time ?? '00:00'}:00`);
    const dateStr = d.toLocaleDateString('pt-BR', {
      weekday: 'long',
      day: '2-digit',
      month: 'long',
      year: 'numeric',
    });
    const capitalizado = dateStr.charAt(0).toUpperCase() + dateStr.slice(1);
    return time ? `${capitalizado} às ${time}` : capitalizado;
  } catch {
    return iso;
  }
}

function relativeDays(iso: string, time?: string | null): string {
  const target = new Date(`${iso}T${time ?? '23:59'}:59`).getTime();
  if (isNaN(target)) return '';
  const diffDays = Math.round((target - Date.now()) / 86400000);
  if (diffDays === 0) return 'Hoje';
  if (diffDays === 1) return 'Amanhã';
  if (diffDays === -1) return 'Ontem';
  return diffDays > 1 ? `Em ${diffDays} dias` : `Há ${Math.abs(diffDays)} dias`;
}

/**
 * A página de uma atividade.
 *
 * Substitui o modal, que só cabia a descrição curta do calendário e cortava o
 * enunciado no meio. Aqui entra a página real da atividade, lida no Moodle com
 * a sessão que o servidor já mantém — é o que poupa o aluno de fazer login de
 * novo só para ler o que precisa entregar.
 *
 * Tem endereço próprio (`/atividade/<chave>`), então dá para favoritar, voltar
 * pelo botão do navegador e mandar o link para um colega: quem abrir vê a
 * atividade se ela estiver na agenda dele, e um 404 se não estiver.
 */
const ActivityPage: React.FC<ActivityPageProps> = ({ stableKey, onBack, onOpenPortal }) => {
  const [detalhe, setDetalhe] = useState<ActivityDetail | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [abrindo, setAbrindo] = useState(false);
  const { isDone, toggleDone } = useDoneEvents();

  useEffect(() => {
    let ativo = true;
    setDetalhe(null);
    setErro(null);

    fetchActivity(stableKey)
      .then((d) => ativo && setDetalhe(d))
      .catch((err) => {
        if (!ativo) return;
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail;
        setErro(detail ?? 'Não consegui carregar esta atividade.');
      });

    return () => {
      ativo = false;
    };
  }, [stableKey]);

  if (erro) {
    return (
      <section className="activity">
        <button type="button" className="btn-back" onClick={onBack}>
          <Icon name="voltar" />
          Voltar para a agenda
        </button>
        <div className="empty-state">{erro}</div>
      </section>
    );
  }

  if (!detalhe) {
    return (
      <section className="activity" aria-busy="true">
        <button type="button" className="btn-back" onClick={onBack}>
          <Icon name="voltar" />
          Voltar para a agenda
        </button>
        <p className="skeleton__status">
          <span className="spinner spinner--dark" aria-hidden="true" />
          Buscando a atividade no Moodle…
        </p>
        <div className="skeleton__heading">
          <div className="skeleton__bar skeleton__bar--title" />
          <div className="skeleton__bar skeleton__bar--subtitle" />
        </div>
      </section>
    );
  }

  const tipo = (TYPE_LABELS[detalhe.type as EventType] ? detalhe.type : 'other') as EventType;

  // O contexto de concluídos é a fonte da verdade na tela: ele reflete o
  // clique na hora, sem esperar uma nova ida ao servidor.
  const comoEvento = {
    id: detalhe.stable_key,
    stable_key: detalhe.stable_key,
    title: detalhe.title,
    date: detalhe.date,
    time: detalhe.time ?? undefined,
    description: detalhe.description,
    subject: detalhe.subject,
    type: tipo,
  } as AcademicEvent;
  const concluido = isDone(comoEvento);

  return (
    <section className="activity">
      <button type="button" className="btn-back" onClick={onBack}>
        <Icon name="voltar" />
        Voltar para a agenda
      </button>

      <header className="activity__header">
        <div className="activity__tags">
          <span className="badge">{TYPE_LABELS[tipo]}</span>
          {concluido && (
            <span className="status-pill status-pill--done">
              <Icon name="check" size={0.9} /> Concluído
            </span>
          )}
        </div>

        <h1 className="activity__title">{detalhe.title}</h1>

        <p className="activity__meta">
          <span>
            <Icon name="prova" size={1} />
            {detalhe.subject}
          </span>
          <span>
            <Icon name="calendario" size={1} />
            {formatFullDate(detalhe.date, detalhe.time)}
          </span>
          <span className="activity__relative">{relativeDays(detalhe.date, detalhe.time)}</span>
        </p>
      </header>

      <div className="activity__actions">
        <button
          type="button"
          className={concluido ? 'btn-secondary' : 'btn-primary'}
          onClick={() => toggleDone(comoEvento)}
        >
          {concluido ? (
            <>
              <Icon name="desfazer" /> Marcar como pendente
            </>
          ) : (
            <>
              <Icon name="check" /> Marcar como concluído
            </>
          )}
        </button>

        {onOpenPortal && detalhe.url && (
          <button
            type="button"
            className="btn-secondary"
            disabled={abrindo}
            onClick={async () => {
              // A aba abre no próprio clique para o navegador não tratar como
              // popup — o link só chega depois, na resposta do backend.
              const aba = window.open('about:blank', '_blank');
              setAbrindo(true);
              try {
                const url = await onOpenPortal(detalhe.subject, detalhe.url);
                if (url && aba) aba.location.href = url;
                else aba?.close();
              } catch {
                aba?.close();
              } finally {
                setAbrindo(false);
              }
            }}
          >
            {abrindo ? (
              <>
                <span className="spinner spinner--dark" aria-hidden="true" /> Abrindo…
              </>
            ) : (
              <>
                <Icon name="link-externo" /> Abrir no Moodle
              </>
            )}
          </button>
        )}
      </div>

      {detalhe.content?.status?.length ? (
        <div className="activity__status">
          <h2 className="activity__section-title">Situação no Moodle</h2>
          <dl>
            {detalhe.content.status.map((linha) => (
              <div key={linha.label}>
                <dt>{linha.label}</dt>
                <dd>{linha.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {detalhe.content?.files?.length ? (
        <div className="activity__files">
          <h2 className="activity__section-title">Arquivos da atividade</h2>
          <ul>
            {detalhe.content.files.map((f) => (
              <li key={f.url}>
                <a href={f.url} target="_blank" rel="noreferrer">
                  <Icon name="entrega" size={1} />
                  {f.name}
                </a>
              </li>
            ))}
          </ul>
          <p className="activity__files-hint">
            Os anexos abrem no Moodle e pedem o login dele — o download acontece no
            navegador, não passa por aqui.
          </p>
        </div>
      ) : null}

      <div className="activity__content">
        <h2 className="activity__section-title">Descritivo da atividade</h2>

        {detalhe.content?.intro ? (
          <Prosa texto={detalhe.content.intro} />
        ) : (
          <>
            {detalhe.content_error && (
              <div className="error-banner" role="alert">
                <Icon name="alerta" />
                {detalhe.content_error}
              </div>
            )}
            {detalhe.description ? (
              <Prosa texto={detalhe.description} />
            ) : (
              <p className="activity__empty">
                O Moodle não devolveu descrição para esta atividade.
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
};

/**
 * O enunciado, com a estrutura que o HTML tinha antes de virar texto.
 *
 * O Moodle escreve o que a atividade pede como lista (`<li>`), e o texto puro
 * entrega isso como linhas soltas terminadas em ";". Renderizar cada uma como
 * parágrafo é o que fazia a página parecer um monte de frases empilhadas sem
 * hierarquia. Aqui as sequências desse tipo voltam a ser uma lista.
 */
const Prosa: React.FC<{ texto: string }> = ({ texto }) => {
  const linhas = texto.split('\n').map((l) => l.trim()).filter(Boolean);
  const blocos: React.ReactNode[] = [];
  let itens: string[] = [];

  const fecharLista = () => {
    if (!itens.length) return;
    blocos.push(
      <ul key={`l${blocos.length}`}>
        {itens.map((item, i) => (
          <li key={i}>{comLinks(item.replace(/^[-•*]\s*/, ''))}</li>
        ))}
      </ul>,
    );
    itens = [];
  };

  for (const linha of linhas) {
    // Item de lista: termina em ";" ou começa com marcador.
    if (/;$/.test(linha) || /^[-•*]\s+/.test(linha)) {
      itens.push(linha);
      continue;
    }

    // Em português a lista fecha com ponto: "a; b; c." Sem esta regra o último
    // item saía da lista e virava um parágrafo solto logo abaixo dela. Uma
    // linha terminada em ":" não entra — essa abre a próxima seção.
    if (itens.length && !linha.endsWith(':')) {
      itens.push(linha);
      fecharLista();
      continue;
    }

    fecharLista();

    // O professor já escreveu a hierarquia; ela só se perdia porque tudo saía
    // com o mesmo peso. Linha terminada em ":" abre uma seção.
    if (linha.endsWith(':') && linha.length < 90) {
      blocos.push(
        <h3 key={`h${blocos.length}`} className="activity__subhead">
          {linha.replace(/:$/, '')}
        </h3>,
      );
      continue;
    }

    // "Peso: 3,0", "Importante: ...", "Formato de entrega: ..." — o rótulo na
    // frente dos dois pontos é o que o olho procura ao varrer o enunciado.
    const rotulado = linha.match(/^([A-ZÀ-Ú][^:]{2,45}):\s+(.+)$/);
    if (rotulado) {
      blocos.push(
        <p key={`p${blocos.length}`}>
          <strong>{rotulado[1]}:</strong> {comLinks(rotulado[2])}
        </p>,
      );
      continue;
    }

    blocos.push(<p key={`p${blocos.length}`}>{comLinks(linha)}</p>);
  }
  fecharLista();

  return <div className="activity__text">{blocos}</div>;
};

/** Transforma URLs soltas no texto em links clicáveis. */
function comLinks(linha: string): React.ReactNode {
  const partes = linha.split(/(https?:\/\/[^\s]+)/g);
  return partes.map((parte, i) =>
    /^https?:\/\//.test(parte) ? (
      <a key={i} href={parte} target="_blank" rel="noopener noreferrer">
        {parte}
      </a>
    ) : (
      <React.Fragment key={i}>{parte}</React.Fragment>
    ),
  );
}

export default ActivityPage;
