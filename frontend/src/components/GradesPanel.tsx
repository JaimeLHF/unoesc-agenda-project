import React, { useEffect, useState } from 'react';
import { fetchGrades } from '../services/api';
import type { Grades } from '../services/api';

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
const GradesPanel: React.FC<GradesPanelProps> = ({ subjectName }) => {
  const [dados, setDados] = useState<Grades | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    setErro(null);
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
