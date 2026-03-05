import React from 'react';
import type { Subject, AcademicEvent } from '../types';

interface SubjectListProps {
  subjects: Subject[];
  events: AcademicEvent[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
}

/**
 * Exibe as disciplinas encontradas como cartões selecionáveis.
 * Permite ao usuário escolher quais disciplinas incluir na sincronização.
 */
const SubjectList: React.FC<SubjectListProps> = ({
  subjects,
  events,
  selectedIds,
  onToggle,
}) => {
  /** Conta quantos eventos pertencem a uma disciplina específica */
  const countEvents = (subjectName: string) =>
    events.filter((e) => e.subject === subjectName).length;

  if (subjects.length === 0) {
    return (
      <div className="empty-state">
        Nenhuma disciplina encontrada no portal.
      </div>
    );
  }

  return (
    <section className="subject-list">
      <h3 className="section-title">Disciplinas encontradas</h3>
      <p className="section-subtitle">
        Selecione as disciplinas cujos eventos deseja sincronizar.
      </p>

      <div className="subject-grid">
        {subjects.map((subject) => {
          const isSelected = selectedIds.has(subject.id);
          const eventCount = countEvents(subject.name);

          return (
            <label
              key={subject.id}
              className={`subject-card ${isSelected ? 'subject-card--selected' : ''}`}
            >
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggle(subject.id)}
                className="subject-checkbox"
              />
              <div className="subject-card-body">
                <span className="subject-name">{subject.name}</span>
                <span className="subject-event-count">
                  {eventCount} {eventCount === 1 ? 'evento' : 'eventos'}
                </span>
              </div>
            </label>
          );
        })}
      </div>
    </section>
  );
};

export default SubjectList;
