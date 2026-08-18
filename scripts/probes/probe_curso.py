"""
Descobre em qual camada a agenda de um curso não-EAD morre.

Motivo: a agenda do amigo de Medicina Veterinária abre vazia e não se sabe se
o problema é matrícula (o Moodle não lista o curso), ausência de atividade com
data (o professor só publica arquivo), ou janela de datas (evento fora dos
2 meses para trás / 6 para frente que o app varre).

Este probe não muda nada — só imprime, camada por camada:

    1. login            → a conta entra no on.unoesc.edu.br?
    2. list_courses     → quantas disciplinas o Moodle devolve?
    3. course_activities→ que módulos existem dentro de cada disciplina?
    4. calendário       → quantos eventos têm data, e de que módulo saem?

A leitura é por diferença: módulo `assign`/`quiz` no passo 3 que não aparece no
passo 4 é atividade sem data marcada; passo 3 só com `resource`/`page`/`url` é
disciplina usada como repositório, e aí não há agenda a montar.

Uso:
    python scripts/probes/probe_curso.py <matrícula> <senha>
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.moodle import MoodleClient, MODULE_TYPE_MAP, clean_course_name  # noqa: E402

# Janela larga de propósito: o app varre -2/+6 meses, e parte do diagnóstico é
# saber se existe evento *fora* dessa janela — o que seria um ajuste trivial,
# ao contrário de "não existe evento nenhum".
MESES_ATRAS = 12
MESES_FRENTE = 12


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    usuario, senha = sys.argv[1], sys.argv[2]

    with MoodleClient() as cliente:
        cliente.login(usuario, senha)
        perfil = cliente.profile()
        print(f"[1] login ok — {perfil.get('name') or usuario}")

        cursos = cliente.list_courses()
        print(f"\n[2] {len(cursos)} disciplina(s) matriculadas")
        for c in cursos:
            print(f"    [{c['course_id']:>6}] {c['name']}")
            print(f"             shortname={c['shortname']!r} dof={c['dof']} "
                  f"start={c['start_date']} end={c['end_date']}")

        print("\n[3] módulos dentro de cada disciplina")
        modulos_totais: Counter = Counter()
        for c in cursos:
            try:
                atividades = cliente.course_activities(c["course_id"])
            except Exception as exc:
                print(f"    {c['name']}: falhou ({exc})")
                continue
            contagem = Counter(a["modname"] for a in atividades)
            modulos_totais.update(contagem)
            resumo = ", ".join(f"{n}x {m}" for m, n in contagem.most_common()) or "vazio"
            print(f"    {c['name']}: {resumo}")
            # Só o que o app trata como compromisso — é o que deveria virar linha
            # na agenda, e por isso vale ver nome a nome.
            for a in atividades:
                if a["modname"] in MODULE_TYPE_MAP:
                    print(f"        · {a['modname']:>10}  {a['name'][:60]}")

        print("\n[3b] módulos somados em todas as disciplinas")
        for mod, n in modulos_totais.most_common():
            marca = "→ vira evento" if mod in MODULE_TYPE_MAP else ""
            print(f"    {n:3}x {mod:20} {marca}")

        print(f"\n[4] calendário ({MESES_ATRAS} meses atrás → {MESES_FRENTE} à frente)")
        brutos = cliente.raw_calendar_events(
            months_back=MESES_ATRAS, months_ahead=MESES_FRENTE
        )
        eventos = cliente.normalize_events(brutos)
        print(f"    {len(eventos)} evento(s) com data")
        for e in eventos:
            print(f"    {e['date']} {e['time']}  {(e['module'] or '?'):14} "
                  f"{(e['event_type'] or ''):6} {e['title'][:44]:46} {e['subject'][:26]}")

        print("\n[4b] eventos por módulo")
        for mod, n in Counter(e["module"] for e in eventos).most_common():
            print(f"    {n:3}x {mod}")
        print("[4c] eventos por disciplina")
        por_curso = Counter(e["subject"] for e in eventos)
        for c in cursos:
            nome = clean_course_name(c["fullname"] or c["shortname"])
            print(f"    {por_curso.get(nome, 0):3}x {nome}")


if __name__ == "__main__":  # pragma: no cover
    main()
