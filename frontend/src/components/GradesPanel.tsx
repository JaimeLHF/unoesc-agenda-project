import React, { useEffect, useState } from 'react';
import { fetchGrades } from '../services/api';
import type { GradeItem, Grades } from '../services/api';

interface GradesPanelProps {
  subjectName: string;
}

function nota(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return '—';
  return valor.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

/**
 * O boletim da disciplina e a conta de quanto falta para passar.
 *
 * A frase de cima é o que o aluno veio buscar; a tabela existe para ele
 * conferir de onde saiu o número. Carrega sob demanda, ao abrir a disciplina:
 * é uma requisição ao Moodle por vez, e ninguém abre seis disciplinas de uma
 * vez só.
 *
 * O que esta tela nunca faz é inventar a conta. O Moodle só dá peso ao item
 * depois de lançar a nota, então na maior parte do semestre não existe base
 * para dizer "precisa de 6,2" — e é melhor dizer que não dá do que produzir um
 * número que faz o aluno relaxar antes da prova que decide.
 */
/**
 * Média final se as avaliações pendentes saírem com as notas do simulador.
 *
 * A fórmula é a mesma do `backend/app/grades.py` — e essa duplicação é
 * deliberada: aqui ela precisa rodar a cada toque no controle, e uma ida ao
 * servidor por arrasto tornaria o simulador inútil. Se a regra de cálculo
 * mudar lá, muda aqui.
 */
function simular(itens: GradeItem[], hipoteses: Record<string, number>): number {
  let total = 0;
  for (const item of itens) {
    const peso = (item.weight ?? 0) / 100;
    const maximo = item.max ?? 10;
    const nota = item.grade ?? hipoteses[item.name] ?? 0;
    if (maximo) total += peso * (nota / maximo) * 10;
  }
  return total;
}

const GradesPanel: React.FC<GradesPanelProps> = ({ subjectName }) => {
  const [dados, setDados] = useState<Grades | null>(null);
  /*
    "E se eu tirar 8 na AV3?" — a pergunta que vem logo depois de "quanto
    falta". O simulador só existe para as avaliações que ainda não têm nota:
    mexer numa nota já lançada seria inventar um boletim.
  */
  const [hipoteses, setHipoteses] = useState<Record<string, number>>({});
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    setErro(null);
    setHipoteses({});
    fetchGrades(subjectName)
      .then((d) => ativo && setDados(d))
      .catch(() => ativo && setErro('Não consegui ler suas notas no Moodle agora.'))
      .finally(() => ativo && setCarregando(false));
    return () => {
      ativo = false;
    };
  }, [subjectName]);

  if (carregando) {
    return <p className="boletim__estado">Lendo suas notas no Moodle…</p>;
  }
  if (erro) {
    return <p className="boletim__estado">{erro}</p>;
  }
  if (!dados || dados.items.length === 0) {
    return <p className="boletim__estado">Esta disciplina ainda não tem nada no boletim.</p>;
  }

  const { current, needed, pending_count, passing_grade } = dados;
  const passou = current !== null && current >= passing_grade && pending_count === 0;
  const pendentes = dados.items.filter((i) => i.grade === null);
  const simulada = simular(dados.items, hipoteses);

  let recado: string;
  if (passou) {
    recado = `Aprovado com ${nota(current)}.`;
  } else if (needed !== null && needed <= 0) {
    recado = `Já garantiu a média — mesmo zerando o que falta, fecha em ${nota(current)}.`;
  } else if (needed !== null && needed > 10) {
    recado = `Não dá mais para chegar a ${passing_grade},0 com o que falta.`;
  } else if (needed !== null) {
    recado = `Precisa de ${nota(needed)} no que falta para fechar em ${passing_grade},0.`;
  } else if (pending_count > 0) {
    recado =
      `Faltam ${pending_count} ${pending_count === 1 ? 'avaliação' : 'avaliações'}, mas o ` +
      'Moodle ainda não deu peso a elas — sem isso não dá para calcular quanto você precisa.';
  } else {
    recado = 'Nada pendente no boletim.';
  }

  return (
    <div className="boletim">
      <p className="boletim__destaque">
        <span className="boletim__nota">{nota(current)}</span>
        <span className="boletim__recado">{recado}</span>
      </p>

      {pendentes.length > 0 && (
        <div className="simulador">
          <p className="simulador__titulo">E se eu tirar…</p>

          {pendentes.map((item) => (
            <label key={item.name} className="simulador__linha">
              <span className="simulador__nome">{item.name}</span>
              <input
                type="range"
                min={0}
                max={item.max ?? 10}
                step={0.5}
                value={hipoteses[item.name] ?? 0}
                onChange={(e) =>
                  setHipoteses((h) => ({ ...h, [item.name]: Number(e.target.value) }))
                }
                aria-label={`Nota simulada em ${item.name}`}
              />
              <span className="simulador__valor">{nota(hipoteses[item.name] ?? 0)}</span>
            </label>
          ))}

          <p
            className={`simulador__resultado simulador__resultado--${
              simulada >= passing_grade ? 'aprovado' : 'reprovado'
            }`}
          >
            Fecharia em <strong>{nota(simulada)}</strong> —{' '}
            {simulada >= passing_grade
              ? `passa em ${passing_grade},0.`
              : `abaixo de ${passing_grade},0.`}
          </p>
        </div>
      )}

      <table className="boletim__tabela">
        <thead>
          <tr>
            <th>Avaliação</th>
            <th>Peso</th>
            <th>Nota</th>
          </tr>
        </thead>
        <tbody>
          {dados.items.map((i) => (
            <tr key={i.name} className={i.grade === null ? 'boletim__linha--pendente' : undefined}>
              <td>{i.name}</td>
              <td>{i.weight !== null ? `${nota(i.weight)}%` : '—'}</td>
              <td>{i.grade !== null ? nota(i.grade) : 'a fazer'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="boletim__rodape">
        Média parcial calculada com os pesos que o Moodle já aplicou. A situação oficial é a
        que a UNOESC publica.
      </p>
    </div>
  );
};

export default GradesPanel;
