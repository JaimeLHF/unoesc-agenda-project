import React from 'react';
import type { AcademicEvent } from '../types';
import Icon from './Icon';
import { useDoneEvents } from '../contexts/DoneEventsContext';
import { cargaDaSemana, descreverCarga, nomeDoDia } from '../lib/semana';

interface SemanaCheiaProps {
  events: AcademicEvent[];
}

/**
 * O aviso de que os próximos sete dias estão pesados.
 *
 * A informação já estava na tela — os eventos aparecem todos —, mas ninguém lê
 * uma lista contando. O aluno descobria que a semana tinha três entregas e uma
 * prova na terça quando já não dava para dividir o esforço.
 *
 * Sete dias a partir de hoje, e não "esta semana" do calendário: na quinta-
 * feira, o que importa não é o que sobra até domingo, é o que vem pela frente.
 *
 * Só aparece quando pesa. Um aviso que aparece toda semana não é aviso.
 */
const SemanaCheia: React.FC<SemanaCheiaProps> = ({ events }) => {
  const { isDone } = useDoneEvents();

  const carga = React.useMemo(
    () => cargaDaSemana(events, new Date(), 7, isDone),
    [events, isDone],
  );

  if (!carga.cheia) return null;

  return (
    <div className="semana-cheia" role="status">
      <span className="semana-cheia__icone" aria-hidden="true">
        <Icon name="alerta" size={1.05} />
      </span>

      <div>
        <p className="semana-cheia__titulo">
          Semana cheia: {descreverCarga(carga)} nos próximos 7 dias
        </p>
        {carga.diaMaisCheio && (
          <p className="semana-cheia__detalhe">
            {carga.diaMaisCheio.quantidade} deles caem no mesmo dia —{' '}
            {nomeDoDia(carga.diaMaisCheio.data)}.
          </p>
        )}
      </div>
    </div>
  );
};

export default SemanaCheia;
