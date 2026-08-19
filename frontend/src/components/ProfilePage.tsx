import React, { useEffect, useState } from 'react';
import Icon from './Icon';
import CalendarFeed from './CalendarFeed';
import InstalarNoCelular from './InstalarNoCelular';
import { fetchProfile } from '../services/api';
import type { Profile } from '../services/api';
import { iniciais } from '../lib/nome';

interface ProfilePageProps {
  onBack: () => void;
}

/** Data por extenso; sem hora quando o dado é só o dia. */
function formatarData(iso: string | null | undefined, comHora = false): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const data = d.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  });
  if (!comHora) return data;
  return `${data} às ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
}

/**
 * A tela de perfil.
 *
 * Junta duas fontes que o aluno enxerga como uma coisa só: o cadastro que está
 * no Moodle (nome, e-mail, departamento, desde quando ele acessa) e o que este
 * app sabe da agenda dele (quantas disciplinas, quanto falta entregar).
 *
 * É tela de leitura, e de propósito. Editar aqui daria a impressão de que a
 * mudança chega ao Moodle, e não chega: cadastro de aluno se altera na
 * secretaria. O rodapé diz isso em voz alta para ninguém tentar.
 */
const ProfilePage: React.FC<ProfilePageProps> = ({ onBack }) => {
  const [perfil, setPerfil] = useState<Profile | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    fetchProfile()
      .then((p) => ativo && setPerfil(p))
      .catch((err) => {
        if (!ativo) return;
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail;
        setErro(detail ?? 'Não consegui carregar seu perfil agora.');
      });
    return () => {
      ativo = false;
    };
  }, []);

  const voltar = (
    <button type="button" className="btn-back" onClick={onBack}>
      <Icon name="voltar" />
      Voltar para a agenda
    </button>
  );

  if (erro) {
    return (
      <section className="profile">
        {voltar}
        <div className="app-banner error-banner" role="alert">
          <Icon name="alerta" />
          {erro}
        </div>
      </section>
    );
  }

  if (!perfil) {
    return (
      <section className="profile" aria-busy="true">
        {voltar}
        <p className="section-subtitle">Carregando seu perfil…</p>
      </section>
    );
  }

  const m = perfil.moodle;
  const nome = m?.fullname || perfil.account_username;
  const stats = perfil.stats;

  // Só entra na lista o que o Moodle realmente preencheu: campo vazio com
  // rótulo bonito vira ruído e faz o aluno procurar o que não existe.
  const dadosMoodle: { rotulo: string; valor: string | null }[] = [
    { rotulo: 'Nome completo', valor: m?.fullname || null },
    { rotulo: 'Matrícula', valor: m?.username || null },
    { rotulo: 'E-mail', valor: m?.email || null },
    { rotulo: 'Departamento', valor: m?.department || null },
    { rotulo: 'Instituição', valor: m?.institution || null },
    { rotulo: 'Cidade', valor: m?.city || null },
    { rotulo: 'Primeiro acesso ao Moodle', valor: formatarData(m?.first_access) },
    { rotulo: 'Último acesso ao Moodle', valor: formatarData(m?.last_access, true) },
  ];

  const dadosConta: { rotulo: string; valor: string | null }[] = [
    { rotulo: 'Login usado aqui', valor: perfil.account_username },
    { rotulo: 'Plano', valor: perfil.plan === 'free' ? 'Gratuito' : perfil.plan },
    { rotulo: 'Usa a Agenda desde', valor: formatarData(perfil.member_since) },
    { rotulo: 'Último acesso ao app', valor: formatarData(perfil.last_login_at, true) },
    { rotulo: 'Agenda atualizada em', valor: formatarData(stats.last_scraped_at, true) },
  ];

  return (
    <section className="profile">
      {voltar}

      <header className="profile__head">
        {m?.avatar ? (
          <img className="profile__avatar" src={m.avatar} alt={`Foto de ${nome}`} />
        ) : (
          <span className="profile__avatar profile__avatar--iniciais" aria-hidden="true">
            {iniciais(nome, perfil.account_username)}
          </span>
        )}
        <div className="profile__identity">
          <h2 className="profile__name">{nome}</h2>
          <p className="profile__email">{m?.email || perfil.account_username}</p>
        </div>
      </header>

      {perfil.moodle_error && (
        <div className="app-banner error-banner" role="alert">
          <Icon name="alerta" />
          {perfil.moodle_error} Seus dados da agenda continuam abaixo.
        </div>
      )}

      <div className="profile__stats">
        <div className="profile__stat">
          <span className="profile__stat-number">{stats.subjects}</span>
          <span className="profile__stat-label">
            {stats.subjects === 1 ? 'disciplina' : 'disciplinas'}
          </span>
        </div>
        <div className="profile__stat">
          <span className="profile__stat-number">{stats.events_upcoming}</span>
          <span className="profile__stat-label">
            {stats.events_upcoming === 1 ? 'entrega pendente' : 'entregas pendentes'}
          </span>
        </div>
        <div className="profile__stat">
          <span className="profile__stat-number">{stats.events_done}</span>
          <span className="profile__stat-label">
            {stats.events_done === 1 ? 'marcada como feita' : 'marcadas como feitas'}
          </span>
        </div>
        <div className="profile__stat">
          <span className="profile__stat-number">{stats.events_total}</span>
          <span className="profile__stat-label">no total da agenda</span>
        </div>
      </div>

      {stats.next_event_title && (
        <div className="profile__next">
          <Icon name="pin" />
          <div>
            <span className="profile__next-label">Próxima entrega</span>
            <strong>{stats.next_event_title}</strong>
            <span className="profile__next-meta">
              {stats.next_event_subject} ·{' '}
              {formatarData(
                `${stats.next_event_date}T${stats.next_event_time ?? '00:00'}:00`,
                Boolean(stats.next_event_time),
              )}
            </span>
          </div>
        </div>
      )}

      <h3 className="profile__section-title">Seus dados no Moodle</h3>
      <dl className="profile__list">
        {dadosMoodle
          .filter((d) => d.valor)
          .map((d) => (
            <div className="profile__row" key={d.rotulo}>
              <dt>{d.rotulo}</dt>
              <dd>{d.valor}</dd>
            </div>
          ))}
      </dl>

      <h3 className="profile__section-title">Sua conta na Agenda</h3>
      <dl className="profile__list">
        {dadosConta
          .filter((d) => d.valor)
          .map((d) => (
            <div className="profile__row" key={d.rotulo}>
              <dt>{d.rotulo}</dt>
              <dd>{d.valor}</dd>
            </div>
          ))}
      </dl>

      <h3 className="profile__section-title">Assinar no seu calendário</h3>
      <CalendarFeed />

      <InstalarNoCelular />

      <p className="profile__note">
        Estes dados são lidos do Moodle a cada visita e não podem ser alterados aqui —
        para corrigir nome, e-mail ou matrícula, fale com a secretaria da UNOESC.
      </p>
    </section>
  );
};

export default ProfilePage;
