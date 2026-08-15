import React, { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import { fetchSubmissionInfo, submitAssignment } from '../services/api';
import type { StatusLinha, SubmissionInfo } from '../services/api';

interface SubmissionBoxProps {
  stableKey: string;
  /** Para quem quiser conferir (ou fazer o envio final) no Moodle. */
  onOpenMoodle?: () => void;
}

function formatarTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * O envio da tarefa, dentro da página da atividade.
 *
 * Salva como **rascunho** no Moodle: o arquivo passa a aparecer na tarefa e dá
 * para trocar ou apagar depois. O "enviar para avaliação" fica de fora de
 * propósito — na maioria das tarefas o aluno não consegue desfazer, e essa não
 * é uma decisão que um app de agenda deva tomar no lugar dele.
 *
 * O "pronto" também não é nosso: depois de salvar, a tela mostra a tabela de
 * status relida no Moodle. Dizer "enviado" sem ter conferido lá seria pior do
 * que não ter o botão — o aluno iria dormir achando que entregou.
 */
const SubmissionBox: React.FC<SubmissionBoxProps> = ({ stableKey, onOpenMoodle }) => {
  const [info, setInfo] = useState<SubmissionInfo | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [texto, setTexto] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [statusSalvo, setStatusSalvo] = useState<StatusLinha[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    fetchSubmissionInfo(stableKey)
      .then((i) => ativo && setInfo(i))
      .catch(() => ativo && setInfo(null))
      .finally(() => ativo && setCarregando(false));
    return () => {
      ativo = false;
    };
  }, [stableKey]);

  if (carregando) {
    return (
      <div className="submission">
        <h2 className="activity__section-title">Enviar</h2>
        <p className="submission__hint">
          <span className="spinner spinner--dark" aria-hidden="true" /> Conferindo o
          envio no Moodle…
        </p>
      </div>
    );
  }

  // Sem formulário de envio não há o que mostrar: webconferência, prova e
  // material não têm entrega, e uma caixa vazia só faria o aluno procurar.
  if (!info) return null;

  if (!info.can_submit) {
    return (
      <div className="submission">
        <h2 className="activity__section-title">Enviar</h2>
        <p className="submission__hint">
          {info.reason ?? 'O Moodle não está aceitando envio nesta tarefa agora.'}
        </p>
      </div>
    );
  }

  const jaAnexados = info.existing_files ?? [];
  // O que já está na tarefa conta no limite do professor: o Moodle salva o
  // conjunto todo, não só o que sobe agora.
  const limiteArquivos = Math.max((info.max_files || 1) - jaAnexados.length, 0);
  const podeEnviar = arquivos.length > 0 || texto.trim().length > 0;

  const adicionar = (lista: FileList | null) => {
    if (!lista) return;
    setErro(null);
    const novos = [...arquivos, ...Array.from(lista)].slice(0, limiteArquivos);
    setArquivos(novos);
  };

  const enviar = async () => {
    setEnviando(true);
    setErro(null);
    try {
      const resultado = await submitAssignment(stableKey, arquivos, texto);
      setStatusSalvo(resultado.status);
      setArquivos([]);
      setTexto('');
      if (inputRef.current) inputRef.current.value = '';
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      setErro(detail ?? 'Não consegui salvar seu envio agora. Tente de novo.');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="submission">
      <h2 className="activity__section-title">Enviar</h2>

      {statusSalvo && (
        <div className="submission__ok" role="status">
          <Icon name="check" />
          <div>
            <strong>Salvo como rascunho no Moodle.</strong>
            <dl className="submission__status">
              {statusSalvo.map((linha) => (
                <div key={linha.label}>
                  <dt>{linha.label}</dt>
                  <dd>{linha.value}</dd>
                </div>
              ))}
            </dl>
            <p className="submission__hint">
              Falta o “enviar para avaliação”, que só o Moodle faz — na maioria das
              tarefas ele não pode ser desfeito, então esse clique fica com você.
              {onOpenMoodle && (
                <>
                  {' '}
                  <button type="button" className="btn-link" onClick={onOpenMoodle}>
                    Abrir a tarefa no Moodle
                  </button>
                </>
              )}
            </p>
          </div>
        </div>
      )}

      {erro && (
        <div className="error-banner" role="alert">
          <Icon name="alerta" />
          {erro}
        </div>
      )}

      {info.accepts_files && jaAnexados.length > 0 && (
        <div className="submission__field">
          <span className="submission__label">
            Já anexado nesta tarefa
            <span className="submission__limits">continua no envio</span>
          </span>
          <ul className="submission__files">
            {jaAnexados.map((f) => (
              <li key={f.name}>
                <Icon name="entrega" size={1} />
                <span className="submission__file-name">{f.name}</span>
                <span className="submission__file-size">{formatarTamanho(f.size)}</span>
              </li>
            ))}
          </ul>
          <p className="submission__hint">
            O que você adicionar abaixo entra junto com estes. Para tirar algum, use o
            Moodle.
          </p>
        </div>
      )}

      {info.accepts_files && limiteArquivos > 0 && (
        <div className="submission__field">
          <label className="submission__label" htmlFor="submission-files">
            Arquivos
            <span className="submission__limits">
              até {limiteArquivos} {limiteArquivos === 1 ? 'arquivo' : 'arquivos'}, {info.max_file_mb} MB cada
            </span>
          </label>
          <input
            id="submission-files"
            ref={inputRef}
            type="file"
            multiple={limiteArquivos > 1}
            disabled={enviando}
            onChange={(e) => adicionar(e.target.files)}
          />

          {arquivos.length > 0 && (
            <ul className="submission__files">
              {arquivos.map((f, i) => (
                <li key={`${f.name}-${i}`}>
                  <Icon name="entrega" size={1} />
                  <span className="submission__file-name">{f.name}</span>
                  <span className="submission__file-size">{formatarTamanho(f.size)}</span>
                  <button
                    type="button"
                    className="btn-icon"
                    disabled={enviando}
                    onClick={() => setArquivos(arquivos.filter((_, j) => j !== i))}
                  >
                    <Icon name="fechar" size={0.9} label={`Tirar ${f.name}`} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {info.accepts_text && (
        <div className="submission__field">
          <label className="submission__label" htmlFor="submission-text">
            Texto online
            <span className="submission__limits">opcional</span>
          </label>
          <textarea
            id="submission-text"
            rows={5}
            value={texto}
            disabled={enviando}
            placeholder="Escreva aqui se a tarefa pedir resposta direto na página."
            onChange={(e) => setTexto(e.target.value)}
          />
        </div>
      )}

      <div className="submission__actions">
        <button
          type="button"
          className="btn-primary"
          disabled={!podeEnviar || enviando}
          onClick={enviar}
        >
          {enviando ? (
            <>
              <span className="spinner" aria-hidden="true" /> Salvando no Moodle…
            </>
          ) : (
            <>
              <Icon name="entrega" /> Salvar envio no Moodle
            </>
          )}
        </button>
        <span className="submission__hint">
          Salva como rascunho — dá para trocar ou apagar depois.
        </span>
      </div>
    </div>
  );
};

export default SubmissionBox;
