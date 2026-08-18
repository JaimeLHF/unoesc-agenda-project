import React, { useState } from 'react';
import Icon from './Icon';
import { fetchCalendarFeed, resetCalendarFeed } from '../services/api';

/**
 * Endereço `.ics` para o aluno assinar a agenda no calendário do celular.
 *
 * O endereço só é criado quando ele clica: enquanto ninguém pede, não existe
 * chave para vazar. Depois de criado, quem tiver o link vê os eventos sem
 * senha nenhuma — é o preço de um endereço que o servidor do Google consegue
 * buscar sozinho —, então o botão de trocar fica ao lado, não escondido.
 */
const CalendarFeed: React.FC = () => {
  const [url, setUrl] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const gerar = async (trocar = false) => {
    setCarregando(true);
    setErro(null);
    try {
      setUrl(trocar ? await resetCalendarFeed() : await fetchCalendarFeed());
      setCopiado(false);
    } catch {
      setErro('Não consegui gerar o endereço agora. Tente de novo em instantes.');
    } finally {
      setCarregando(false);
    }
  };

  const copiar = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopiado(true);
    } catch {
      // Sem permissão de área de transferência (Safari em página não segura,
      // por exemplo): o endereço está na tela e dá para selecionar à mão.
      setCopiado(false);
    }
  };

  return (
    <div className="feed">
      <p className="feed__intro">
        Cole este endereço no Google Agenda, no Calendário do iPhone ou no Outlook e seus
        prazos aparecem lá — atualizados sozinhos, algumas vezes por dia.
      </p>

      {url ? (
        <>
          <div className="feed__url">
            <code>{url}</code>
            <button type="button" className="btn-ghost" onClick={copiar}>
              <Icon name={copiado ? 'check' : 'link-externo'} size={0.95} />
              {copiado ? 'Copiado' : 'Copiar'}
            </button>
          </div>
          <p className="feed__aviso">
            Quem tiver este endereço vê seus prazos, sem precisar de senha. Se ele vazar,
            gere outro — o antigo para de funcionar na hora.
          </p>
          <button
            type="button"
            className="btn-ghost"
            onClick={() => gerar(true)}
            disabled={carregando}
          >
            Gerar outro endereço
          </button>
        </>
      ) : (
        <button
          type="button"
          className="btn-primary"
          onClick={() => gerar(false)}
          disabled={carregando}
        >
          {carregando ? 'Gerando…' : 'Criar endereço do calendário'}
        </button>
      )}

      {erro && <p className="feed__erro">{erro}</p>}
    </div>
  );
};

export default CalendarFeed;
