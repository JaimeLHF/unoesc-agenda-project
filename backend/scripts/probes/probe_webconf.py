#!/usr/bin/env python3
"""
Procura webconferências no texto das disciplinas.

O calendário do Moodle só conhece atividades (assign/quiz). Webconferência é
anunciada no texto da página do curso, e era isso que o Gemini garimpava. Este
script mostra o texto cru ao redor de cada menção, para decidir se dá para
extrair com regra fixa em vez de LLM.

Uso:  cd backend && .venv/bin/python scripts/probes/probe_webconf.py
"""
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.moodle import MoodleClient, _normalizar  # noqa: E402

# O que caracteriza um encontro ao vivo no texto
GATILHOS = ("webconf", "web conf", "videoconf", "conferencia", "encontro online",
            "aula online", "ao vivo", "meet", "zoom", "teams")

# Data em vários formatos: 04/08, 04/08/2026, "4 de agosto"
DATA = re.compile(
    r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    r"|\d{1,2}\s+de\s+(?:janeiro|fevereiro|março|abril|maio|junho|julho|agosto"
    r"|setembro|outubro|novembro|dezembro))",
    re.IGNORECASE,
)
HORA = re.compile(r"(\d{1,2})\s*[h:]\s*(\d{2})?")


def main() -> int:
    usuario = input("Usuário do Moodle: ").strip()
    senha = getpass.getpass("Senha: ")

    with MoodleClient() as cliente:
        cliente.login(usuario, senha)
        cursos = cliente.list_courses()
        print(f"\n{len(cursos)} disciplinas\n" + "=" * 72)

        total_mencoes = com_data = 0

        for c in cursos:
            texto = cliente.course_text(c["course_id"])
            linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]

            achados = []
            for i, linha in enumerate(linhas):
                if not any(g in _normalizar(linha) for g in GATILHOS):
                    continue
                # Junta a linha com as duas seguintes: a data costuma vir depois
                contexto = " ".join(linhas[i:i + 3])[:300]
                datas = DATA.findall(contexto)
                horas = HORA.findall(contexto)
                achados.append((linha[:90], datas, horas, contexto))

            if not achados:
                continue

            print(f"\n[{c['course_id']}] {c['name']}")
            for linha, datas, horas, contexto in achados:
                total_mencoes += 1
                marca = "✓ tem data" if datas else "· sem data no contexto"
                if datas:
                    com_data += 1
                print(f"    {marca}")
                print(f"      linha : {linha}")
                if datas:
                    print(f"      datas : {datas}")
                if horas:
                    print(f"      horas : {[':'.join(filter(None, h)) for h in horas]}")
                print(f"      volta : {contexto[:200]}")

        print("\n" + "=" * 72)
        print(f"menções a encontro ao vivo: {total_mencoes}")
        print(f"  com data extraível:       {com_data}")
        print()
        if total_mencoes == 0:
            print("→ Nenhuma menção no texto das páginas. As webconferências do banco")
            print("  antigo vieram de outro lugar (descrição de seção? PDF?) — nesse")
            print("  caso nem o Gemini reencontraria hoje.")
        elif com_data == 0:
            print("→ Há menções, mas sem data no texto ao redor. Regra fixa não resolve;")
            print("  só LLM (ou entrada manual) recupera esses eventos.")
        else:
            print(f"→ {com_data} menções têm data no texto. Dá para extrair com regra")
            print("  fixa, sem LLM e sem chave de API. Vale implementar no MoodleClient.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
