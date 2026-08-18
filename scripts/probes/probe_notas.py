"""
Descobre se o Moodle da UNOESC entrega situação acadêmica (Aprovado / Em Exame
/ Reprovado) para o aluno logado.

Motivo: as funções de nota do AJAX respondem `servicenotavailable` nesta
instância (medido em 15/08/2026), então a única chance é a página HTML do
relatório de notas. Este probe não muda nada — só imprime o que vem — para
decidir se dá para mostrar o status no card da disciplina.

Uso:
    python scripts/probes/probe_notas.py <matrícula> <senha>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.moodle import MoodleClient, html_to_text, main_region  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)

    cliente = MoodleClient()
    cliente.login(sys.argv[1], sys.argv[2])

    print("== visão geral de notas (todos os cursos) ==")
    resp = cliente._client.get(f"{cliente.base}/grade/report/overview/index.php")
    print("HTTP", resp.status_code)
    print(html_to_text(main_region(resp.text))[:3000])

    for curso in cliente.list_courses()[:3]:
        print(f"\n== notas de {curso['name']} ({curso['course_id']}) ==")
        resp = cliente._client.get(
            f"{cliente.base}/grade/report/user/index.php",
            params={"id": curso["course_id"]},
        )
        print("HTTP", resp.status_code)
        print(html_to_text(main_region(resp.text))[:2000])


if __name__ == "__main__":
    main()
