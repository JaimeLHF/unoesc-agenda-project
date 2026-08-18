import React, { useState } from 'react';
import { setReminders } from '../services/api';

interface ReminderToggleProps {
  /** Estado que veio do perfil. */
  enabled: boolean;
  /** Endereço para onde o aviso iria; nulo quando o Moodle não respondeu. */
  email: string | null;
}

/**
 * Liga o aviso por e-mail na véspera do prazo.
 *
 * Nasce desligado e diz para qual endereço o e-mail vai antes de ligar — um
 * aviso que chega num endereço que o aluno não abre é pior que nenhum, porque
 * ele passa a confiar num lembrete que não vê.
 */
const ReminderToggle: React.FC<ReminderToggleProps> = ({ enabled, email }) => {
  const [ligado, setLigado] = useState(enabled);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const alternar = async () => {
    const novo = !ligado;
    setSalvando(true);
    setErro(null);
    try {
      setLigado(await setReminders(novo));
    } catch {
      setErro('Não consegui salvar agora. Tente de novo em instantes.');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="lembrete">
      <label className="lembrete__linha">
        <input
          type="checkbox"
          checked={ligado}
          onChange={alternar}
          disabled={salvando || !email}
        />
        <span>
          Me avisar por e-mail na véspera de cada prazo
          {email && <span className="lembrete__email">{email}</span>}
        </span>
      </label>

      {!email && (
        <p className="lembrete__nota">
          Preciso do seu e-mail do Moodle para isso, e ele não veio nesta visita. Recarregue
          o perfil quando o Moodle estiver respondendo.
        </p>
      )}

      {erro && <p className="lembrete__erro">{erro}</p>}
    </div>
  );
};

export default ReminderToggle;
