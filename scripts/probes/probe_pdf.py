"""
Roda o garimpo de prazos num PDF que você já tem na máquina.

Serve para testar o extrator com material de outros cursos sem precisar da
conta do aluno: peça o PDF da disciplina, salve em qualquer pasta e rode aqui.
Se sair prazo errado ou faltando, o arquivo vira caso de teste em
`backend/tests/test_schedule_pdf.py`.

Uso:
    python scripts/probes/probe_pdf.py <arquivo.pdf> [outro.pdf ...]
    python scripts/probes/probe_pdf.py --texto <arquivo.pdf>   # mostra o texto lido

`--texto` é o primeiro lugar para olhar quando não sai nada: PDF que devolve
texto vazio é lâmina escaneada (imagem), e aí não há regex que resolva.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.schedule_pdf import (  # noqa: E402
    extract_schedule,
    looks_like_schedule,
    pdf_to_text,
)


def analisar(caminho: Path, mostrar_texto: bool) -> int:
    print(f"\n=== {caminho.name} ===")
    if not caminho.exists():
        print("  arquivo não encontrado")
        return 0

    nome = caminho.stem
    print(f"  o nome do arquivo seria escolhido pelo app? "
          f"{'sim' if looks_like_schedule(nome) else 'não — cairia no primeiro arquivo da sala'}")

    texto = pdf_to_text(caminho.read_bytes())
    print(f"  {len(texto)} caracteres de texto extraídos")
    if not texto.strip():
        print("  → sem texto: provavelmente lâmina escaneada (imagem). Nada a garimpar.")
        return 0

    if mostrar_texto:
        print("  ---- texto ----")
        for linha in texto.splitlines():
            if linha.strip():
                print(f"  | {linha}")
        print("  ---------------")

    eventos = extract_schedule(texto, "DISCIPLINA", "http://exemplo", 0, origem=nome)
    print(f"  {len(eventos)} prazo(s) encontrados:")
    for e in eventos:
        print(f"    {e['date']}  {e['type']:8}  {e['title']}")
    return len(eventos)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--texto"]
    mostrar_texto = "--texto" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)

    total = sum(analisar(Path(a), mostrar_texto) for a in args)
    print(f"\ntotal: {total} prazo(s) em {len(args)} arquivo(s)")


if __name__ == "__main__":  # pragma: no cover
    main()
