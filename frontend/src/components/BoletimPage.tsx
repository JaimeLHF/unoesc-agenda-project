import React from 'react';
import Icon from './Icon';
import type { Subject } from '../types';

interface BoletimPageProps {
  subjects: Subject[];
  onBack: () => void;
  /** Abre a disciplina, onde ficam o boletim item a item e o simulador. */
  onSelectSubject: (id: string) => void;
}

const ORDEM: Record<string, number> = {
  impossivel: 0,
  precisa: 1,
  sem_base: 2,
  garantido: 3,
  fechado: 4,
};

const ROTULO: Record<string, string> = {
  impossivel: 'Em risco',
  precisa: 'Depende do que falta',
  sem_base: 'Sem base para calcular',
  garantido: 'Garantida',
  fechado: 'Encerrada',
};

function nota(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return '—';
  return valor.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

/**
 * Todas as notas do semestre numa tela.
 *
 * O cartão de cada disciplina já diz quanto falta, mas espalhado pela grade —
 * e a pergunta "como estou no semestre?" é sobre o conjunto: qual disciplina
 * está em risco, qual já está garantida, onde vale gastar o fim de semana.
 * Aqui elas aparecem juntas, do mais urgente para o mais tranquilo.
 *
 * Não busca nada: monta com o que a agenda já tem em memória. Por isso abre
 * instantânea, e por isso uma disciplina sem boletim guardado aparece como
 * "sem base" em vez de sumir — some da conta, não da lista.
 */
const BoletimPage: React.FC<BoletimPageProps> = ({ subjects, onBack, onSelectSubject }) => {
  const ordenadas = [...subjects].sort((a, b) => {
    const pa = ORDEM[a.grade_status ?? 'sem_base'] ?? 9;
    const pb = ORDEM[b.grade_status ?? 'sem_base'] ?? 9;
    return pa - pb || a.name.localeCompare(b.name);
  });

  const comConta = ordenadas.filter((s) => typeof s.grade_current === 'number');
  const media =
    comConta.length > 0
      ? comConta.reduce((soma, s) => soma + (s.grade_current ?? 0), 0) / comConta.length
      : null;

  return (
    <section className="boletim-semestre">
      <button type="button" className="btn-back" onClick={onBack}>
        <Icon name="voltar" />
        Voltar para a agenda
      </button>

      <div className="page-heading">
        <h2 className="section-title">Suas notas no semestre</h2>
        <p className="section-subtitle">
          {media !== null
            ? `Média parcial de ${nota(media)} nas ${comConta.length} disciplinas com nota lançada.`
            : 'Nenhuma nota lançada ainda neste semestre.'}
        </p>
      </div>

      <ul className="boletim-semestre__lista">
        {ordenadas.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              className={`boletim-semestre__item boletim-semestre__item--${
                s.grade_status ?? 'sem_base'
              }`}
              onClick={() => onSelectSubject(s.id)}
            >
              <span className="boletim-semestre__nome">{s.name}</span>
              <span className="boletim-semestre__situacao">
                {ROTULO[s.grade_status ?? 'sem_base'] ?? 'Sem base para calcular'}
              </span>
              <span className="boletim-semestre__nota">{nota(s.grade_current)}</span>
              <span className="boletim-semestre__frase">
                {s.grade_forecast ?? 'Abra a disciplina para o app ler o boletim dela.'}
              </span>
            </button>
          </li>
        ))}
      </ul>

      <p className="boletim-semestre__rodape">
        As médias saem do boletim do Moodle e são calculadas com os pesos que ele já aplicou.
        A situação oficial é a que a UNOESC publica.
      </p>
    </section>
  );
};

export default BoletimPage;
