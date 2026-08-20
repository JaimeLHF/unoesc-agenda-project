import React, { useCallback, useEffect, useState } from 'react';
import Icon from './Icon';
import { fetchPanorama } from '../services/api';
import type { AdminPanorama } from '../services/api';

interface AdminPageProps {
  onBack: () => void;
}

/** De quanto em quanto tempo a tela se atualiza sozinha, aberta. */
const INTERVALO_MS = 60_000;

/**
 * O SQLite guarda data sem fuso, e `new Date('2026-08-20 11:00:00')` no
 * navegador assume o fuso de quem está olhando — três horas de erro em toda
 * linha da tabela. O backend grava em UTC, então é isso que dizemos aqui.
 */
function paraData(bruto: string): Date {
  const tem_fuso = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(bruto);
  return new Date(tem_fuso ? bruto : `${bruto.replace(' ', 'T')}Z`);
}

/** "há 3h" — o instante exato não responde "isso é recente?". */
function quando(bruto: string): string {
  const d = paraData(bruto);
  if (isNaN(d.getTime())) return bruto;
  const min = Math.floor((Date.now() - d.getTime()) / 60000);
  if (min < 2) return 'agora';
  if (min < 60) return `há ${min}min`;
  if (min < 60 * 24) return `há ${Math.floor(min / 60)}h`;
  if (min < 60 * 24 * 30) return `há ${Math.floor(min / 1440)}d`;
  return d.toLocaleDateString('pt-BR');
}

function duracao(segundos: number): string {
  if (segundos < 60) return `${segundos}s`;
  if (segundos < 3600) return `${Math.floor(segundos / 60)}min`;
  if (segundos < 86400) return `${Math.floor(segundos / 3600)}h`;
  return `${Math.floor(segundos / 86400)}d`;
}

function ms(valor: number | null): string {
  return valor === null ? '—' : `${Math.round(valor)}ms`;
}

/**
 * Painel do dono do serviço.
 *
 * Existe porque a pergunta "alguém está usando isso, e está funcionando?" não
 * tinha resposta sem abrir um terminal e consultar o banco na mão. É a única
 * tela do app que mostra dado de mais de um aluno — e por isso o backend a
 * fecha por matrícula (`ADMIN_USERNAMES`) e responde 404, não 403, para todo
 * o resto do mundo.
 *
 * Ela lê ao vivo a cada carregamento e se atualiza sozinha de minuto em
 * minuto: um painel que mostra número velho sem avisar é pior que não ter
 * painel, porque parece atual.
 */
const AdminPage: React.FC<AdminPageProps> = ({ onBack }) => {
  const [dados, setDados] = useState<AdminPanorama | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [lido, setLido] = useState<Date | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setDados(await fetchPanorama());
      setLido(new Date());
      setErro(null);
    } catch {
      setErro('Não foi possível ler o painel. O servidor respondeu com erro.');
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
    const id = window.setInterval(() => void carregar(), INTERVALO_MS);
    return () => window.clearInterval(id);
  }, [carregar]);

  const voltar = (
    <button type="button" className="btn-back" onClick={onBack}>
      <Icon name="voltar" />
      Voltar para a agenda
    </button>
  );

  if (erro && !dados) {
    return (
      <section className="admin">
        {voltar}
        <div className="app-banner error-banner" role="alert">
          <Icon name="alerta" />
          {erro}
        </div>
      </section>
    );
  }

  if (!dados) {
    return (
      <section className="admin" aria-busy="true">
        {voltar}
        <p className="admin-vazio">Lendo o estado do serviço…</p>
      </section>
    );
  }

  const { resumo, contas, por_dia: porDia, servidor } = dados;

  return (
    <section className="admin">
      {voltar}

      <header className="admin-topo">
        <div>
          <h2>Painel do serviço</h2>
          <p className="admin-legenda">
            Ao vivo, do banco de produção
            {lido && ` · lido ${quando(lido.toISOString())}`}
          </p>
        </div>
        <button
          type="button"
          className="admin-atualizar"
          onClick={() => void carregar()}
          disabled={carregando}
        >
          <Icon name="atualizar" />
          {carregando ? 'Lendo…' : 'Atualizar'}
        </button>
      </header>

      <div className="admin-cartoes">
        <Cartao valor={resumo.total} rotulo="contas criadas"
                nota={resumo.novos_hoje ? `+${resumo.novos_hoje} hoje` : ''} />
        <Cartao valor={resumo.ativos_24h} rotulo="entraram em 24h" />
        <Cartao valor={resumo.ativos_7d} rotulo="entraram em 7 dias" />
        <Cartao valor={resumo.sessoes_vivas} rotulo="sessões abertas" />
        <Cartao
          valor={resumo.aparelhos}
          rotulo="aparelhos com aviso"
          nota={
            (resumo.push_alunos ? `${resumo.push_alunos} aluno(s)` : '') +
            (resumo.push_falhando ? ` · ${resumo.push_falhando} falhando` : '')
          }
        />
      </div>

      <h3 className="admin-secao">Contas</h3>
      <div className="admin-quadro admin-rolagem">
        <table className="admin-tabela">
          <thead>
            <tr>
              <th>aluno</th>
              <th>último acesso</th>
              <th>entrou</th>
              <th className="num">disc.</th>
              <th className="num">eventos</th>
              <th className="num">feitos</th>
              <th>avisos</th>
              <th>.ics</th>
              <th className="num">Lumi</th>
            </tr>
          </thead>
          <tbody>
            {contas.map((c) => (
              <tr key={c.username}>
                <td>
                  <span className="admin-nome">
                    {c.nome || 'sem nome ainda'}
                    {c.sessoes > 0 && <span className="admin-online" title="sessão aberta" />}
                  </span>
                  <span className="mono admin-matricula">{c.username}</span>
                </td>
                <td>{quando(c.ultimo_acesso)}</td>
                <td>{quando(c.criado_em)}</td>
                <td className="num">{c.disciplinas}</td>
                <td className="num">{c.eventos}</td>
                <td className="num">{c.concluidos}</td>
                <td>{c.aparelhos > 0 ? `${c.aparelhos}` : '—'}</td>
                <td>{c.assinou_ics ? 'sim' : '—'}</td>
                <td className="num">{c.lumi}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="admin-secao">Servidor</h3>
      <div className="admin-duas">
        <div className="admin-quadro">
          <p className="admin-legenda">
            De pé há {duracao(servidor.uptime_s)} · {servidor.requisicoes} requisições
          </p>
          <p className="admin-numeros">
            mediana <b>{ms(servidor.p50_ms)}</b> · p95 <b>{ms(servidor.p95_ms)}</b> ·
            pior <b>{ms(servidor.max_ms)}</b>
          </p>
          <p className="admin-legenda">
            A contagem começa a cada deploy: ela vive na memória do processo.
          </p>
          {servidor.lentas.length > 0 && (
            <>
              <p className="admin-legenda">Passaram de 1 segundo:</p>
              <ul className="admin-lista">
                {servidor.lentas.map((l, i) => (
                  <li key={`${l.rota}-${i}`}>
                    <span className="mono">{l.rota}</span> — <b>{l.ms}ms</b>{' '}
                    <span className="admin-legenda">{quando(l.quando)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <div className="admin-quadro admin-rolagem">
          <p className="admin-legenda">Rotas mais chamadas</p>
          <table className="admin-tabela">
            <tbody>
              {servidor.por_rota.map(([rota, n]) => (
                <tr key={rota}>
                  <td className="mono">{rota}</td>
                  <td className="num">{n}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="admin-legenda">
            {servidor.por_status.map(([status, n]) => `${status}: ${n}`).join(' · ')}
          </p>
        </div>
      </div>

      <h3 className="admin-secao">Falhas registradas</h3>
      <div className="admin-quadro">
        {servidor.falhas.length === 0 ? (
          <p className="admin-vazio">
            Nenhuma falha desde que o processo subiu.
          </p>
        ) : (
          <ul className="admin-lista">
            {servidor.falhas.map((f) => (
              <li key={f.codigo}>
                <span className="mono">{f.codigo}</span> · {f.contexto}
                <div className="admin-erro">{f.erro}</div>
                <span className="admin-legenda">{quando(f.quando)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <h3 className="admin-secao">Dados guardados</h3>
      <div className="admin-cartoes">
        <Cartao valor={resumo.disciplinas} rotulo="disciplinas" />
        <Cartao valor={resumo.eventos} rotulo="eventos"
                nota={`${resumo.eventos_pdf} vindos de PDF`} />
        <Cartao valor={resumo.itens_sala} rotulo="itens de sala" />
      </div>

      <h3 className="admin-secao">Contas novas por dia</h3>
      <div className="admin-quadro">
        <ul className="admin-lista">
          {porDia.map((d) => (
            <li key={d.dia}>
              <span className="mono">{d.dia}</span> — {d.contas} conta(s)
            </li>
          ))}
        </ul>
      </div>

      <p className="admin-rodape">
        Esta tela mostra o nome e a matrícula de quem usa o app. Ela existe para manter o
        serviço no ar — não para acompanhar aluno. O conteúdo da agenda de cada
        um continua fora daqui.
      </p>
    </section>
  );
};

const Cartao: React.FC<{ valor: number; rotulo: string; nota?: string }> = ({
  valor,
  rotulo,
  nota,
}) => (
  <div className="admin-cartao">
    <div className="admin-valor">{valor}</div>
    <div className="admin-rotulo">{rotulo}</div>
    {nota ? <div className="admin-nota">{nota}</div> : null}
  </div>
);

export default AdminPage;
