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

# O que estamos procurando: se alguma dessas palavras aparecer, existe status
# acadêmico para mostrar no card. Só nota numérica não resolve — "Aprovado" é
# uma decisão da UNOESC, não do Moodle.
PISTAS = ("situa", "aprovad", "reprovad", "exame", "conceito", "final")


def destacar(texto: str) -> None:
    achou = [
        linha.strip()
        for linha in texto.splitlines()
        if any(p in linha.lower() for p in PISTAS) and linha.strip()
    ]
    print("--- linhas com pista de status ---")
    print("\n".join(achou[:40]) or "(nenhuma)")


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)

    cliente = MoodleClient()
    cliente.login(sys.argv[1], sys.argv[2])

    print("== visão geral de notas (todos os cursos) ==")
    resp = cliente._client.get(f"{cliente.base}/grade/report/overview/index.php")
    print("HTTP", resp.status_code)
    texto = html_to_text(main_region(resp.text))
    print(texto[:2000])
    destacar(texto)

    for curso in cliente.list_courses()[:3]:
        print(f"\n== notas de {curso['name']} ({curso['course_id']}) ==")
        resp = cliente._client.get(
            f"{cliente.base}/grade/report/user/index.php",
            params={"id": curso["course_id"]},
        )
        print("HTTP", resp.status_code)
        texto = html_to_text(main_region(resp.text))
        print(texto[:1200])
        destacar(texto)


if __name__ == "__main__":
    main()
