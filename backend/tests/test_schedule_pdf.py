"""
Garimpo de prazos no PDF da disciplina — `app.schedule_pdf`.

Roda sem rede e sem PDF: a entrada é o texto já extraído, que é onde mora toda
a decisão. O trecho abaixo é cópia literal da lâmina de avaliações do PDF
"Aula 1 - Apresentação da disciplina Medicina de Pequenos Animais", conta de
Medicina Veterinária, medida em 18/08/2026.

    cd backend && python -m tests.test_schedule_pdf

Sai com código 1 na primeira falha.
"""

import sys
from datetime import datetime

from app.schedule_pdf import TZ_BR, extract_schedule, looks_like_schedule

# Data fixa: a extração descarta o que cai fora da janela em torno de "hoje",
# e um teste que depende do relógio começa a falhar sozinho ano que vem.
HOJE = datetime(2026, 8, 18, tzinfo=TZ_BR)

LAMINA = """AVALIAÇÕES 2026 – TURMA A
▪ A1/1 Avaliação teórica - Prof. Andressa 10/09/2026 – Peso: 4
▪ A1/2 Avaliação teórica - Prof. Juliano 24/11/2026 – Peso: 4
▪ A1/3 Confecção de bulário 28/07/2026 á 25/11/2026 – Peso 0,2
▪ A1/4 Relatório e participação de aulas práticas 11/11/2026 a 25/11/2026 – Peso: 0,3
▪ A1/5 Realização do Autoestudo 28/07/2026 a 25/11/2026 – Peso: 0,5
▪ A1/6 Atividades práticas de extensão (APEX) – Peso: 1
"""

# Bibliografia e rodapé: tudo que tem número mas não é prazo.
RUIDO = """▪ ANDRADE, S.F. “MANUAL DE TERAPÊUTICA VETERINÁRIA”. 2ED. SÃO PAULO: ED. ROCA, 2002.
▪ TILLEY, L.P. MANUAL DE CARDIOLOGIA. 3ED. ROCA, 489P., 2002.
Documento revisado em 03/02/1998
Prova final 31/02/2026
São Miguel do Oeste
"""

falhas: list[str] = []


def verificar(condicao: bool, descricao: str) -> None:
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        falhas.append(descricao)


def main_teste() -> int:
    print("[1] A lâmina de avaliações vira agenda")
    eventos = extract_schedule(
        LAMINA, "MEDICINA DE PEQUENOS ANIMAIS",
        "https://on.unoesc.edu.br/course/view.php?id=9575",
        course_id=9575, origem="Aula 1 - Apresentação", hoje=HOJE,
    )
    por_titulo = {e["title"]: e for e in eventos}

    verificar(len(eventos) == 5, f"5 linhas com data viram 5 eventos (vieram {len(eventos)})")
    verificar("A1/6 Atividades práticas de extensão (APEX)" not in por_titulo,
              "linha sem data nenhuma fica de fora")

    prova = por_titulo.get("A1/1 Avaliação teórica - Prof. Andressa")
    verificar(prova is not None, "o título sobrevive inteiro, sem comer a última letra")
    verificar(prova is not None and prova["date"] == "2026-09-10", "data única vira o prazo")
    verificar(prova is not None and prova["type"] == "exam", "avaliação é classificada como prova")
    verificar(prova is not None and prova["time"] is None,
              "sem hora: o PDF não diz, e o app não inventa")

    bulario = por_titulo.get("A1/3 Confecção de bulário")
    verificar(bulario is not None, "o conector solto do intervalo (“á”) sai do título")
    verificar(bulario is not None and bulario["date"] == "2026-11-25",
              "intervalo vira um evento só, na data final")
    verificar(bulario is not None and "28/07/2026" in bulario["description"],
              "o período inteiro fica na descrição")
    verificar(bulario is not None and bulario["type"] == "deadline",
              "entrega que não é prova vira prazo")

    print("\n[2] Identidade do evento")
    de_novo = extract_schedule(
        LAMINA, "MEDICINA DE PEQUENOS ANIMAIS", "u", course_id=9575, hoje=HOJE,
    )
    verificar([e["moodle_event_id"] for e in eventos] == [e["moodle_event_id"] for e in de_novo],
              "a chave é estável entre duas leituras do mesmo arquivo")

    adiada = LAMINA.replace("10/09/2026", "17/09/2026")
    nova = extract_schedule(adiada, "MEDICINA DE PEQUENOS ANIMAIS", "u",
                            course_id=9575, hoje=HOJE)
    chave_antes = por_titulo["A1/1 Avaliação teórica - Prof. Andressa"]["moodle_event_id"]
    chave_depois = next(e["moodle_event_id"] for e in nova
                        if e["title"].startswith("A1/1"))
    verificar(chave_antes == chave_depois,
              "professor que adia a prova atualiza o evento, não duplica")
    verificar(all(e["source"] == "pdf_curso" for e in eventos),
              "a origem fica marcada como PDF, para a tela poder avisar")

    print("\n[3] Ruído não vira compromisso")
    ruido = extract_schedule(RUIDO, "DISCIPLINA", "u", course_id=1, hoje=HOJE)
    titulos = [e["title"] for e in ruido]
    verificar(ruido == [], f"bibliografia, data velha e 31/02 são descartadas ({titulos})")

    print("\n[4] Escolha do arquivo pelo nome")
    verificar(looks_like_schedule("Aula 1 - Apresentação da disciplina PDF"),
              "apresentação da disciplina é candidata")
    verificar(looks_like_schedule("Plano de Ensino 2026-2.pdf"), "plano de ensino é candidato")
    verificar(not looks_like_schedule("Dermatologia canina - capítulo 3"),
              "material de conteúdo não é candidato")

    print()
    if falhas:
        print(f"❌ {len(falhas)} verificação(ões) falharam:")
        for f in falhas:
            print(f"   - {f}")
        return 1
    print("✅ todas as verificações passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main_teste())
