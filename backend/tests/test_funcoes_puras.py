"""
Funções puras que a agenda inteira depende — nome de disciplina, tipo de
evento, chave do evento e os parsers de HTML do Moodle.

Nenhuma delas fala com a rede, e todas quebram calado: se o Moodle mudar o
layout ou o padrão do nome de curso, o app continua respondendo 200 e mostra
agenda errada. Este arquivo é o alarme.

    cd backend && python -m tests.test_funcoes_puras

Sai com código 1 na primeira falha.
"""

import sys
from datetime import datetime

from app import push
from app.database import event_key, moodle_event_key, stable_event_key
from app.moodle import (
    TZ_BR,
    MoodleClient,
    clean_course_name,
    clean_event_title,
    dof_from_shortname,
    extract_webconferences,
    guess_type,
)

falhas: list[str] = []


def verificar(condicao: bool, descricao: str) -> None:
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        falhas.append(descricao)


def igual(obtido, esperado, descricao: str) -> None:
    verificar(obtido == esperado, descricao if obtido == esperado
              else f"{descricao} (obtido: {obtido!r})")


def main_teste() -> int:
    print("[1] Nome da disciplina")
    # O Moodle devolve "código - NOME - turma"; o aluno só reconhece o do meio,
    # e é esse nome que casa o evento com o cartão da disciplina na tela.
    igual(clean_course_name("10275 - ENGENHARIA DE SOFTWARE - EAD54-12"),
          "ENGENHARIA DE SOFTWARE", "código na frente e turma no fim saem")
    igual(clean_course_name("36798 - MEDICINA DE PEQUENOS ANIMAIS - SMO34-5B"),
          "MEDICINA DE PEQUENOS ANIMAIS", "turma de curso presencial também sai")
    igual(clean_course_name("BANCO DE DADOS (DOF_1414949)"), "BANCO DE DADOS",
          "o DOF no meio do nome sai")
    igual(clean_course_name(""), "Disciplina", "nome vazio não vira string vazia")

    print("\n[2] DOF, que vem escondido no shortname")
    igual(dof_from_shortname("28743 - EAD54-12 (DOF_1414949)"), "1414949",
          "DOF_ com underline")
    igual(dof_from_shortname("SMO34-5"), None, "sem DOF devolve None, não erro")

    print("\n[3] Título do evento sem a frase do Moodle")
    igual(clean_event_title("Atividade 3 está marcado(a) para esta data"),
          "Atividade 3", "sufixo em português sai")
    igual(clean_event_title("Questionário 2 deve ser entregue nesta data"),
          "Questionário 2", "o outro sufixo também")
    igual(clean_event_title(""), "Evento", "título vazio tem substituto")

    print("\n[4] Tipo do evento")
    igual(guess_type("assign", "qualquer"), "deadline", "assign é entrega")
    igual(guess_type("quiz", "qualquer"), "exam", "quiz é prova")
    igual(guess_type("forum", "qualquer"), "deadline", "fórum tem prazo")
    # O módulo manda; o título só desempata. Um arquivo chamado "Aula On-line"
    # é material de leitura, não encontro ao vivo.
    igual(guess_type("resource", "Aula On-line 3 - slides"), "other",
          "material não vira compromisso por causa do título")
    igual(guess_type("url", "Webconferência 2"), "webconference",
          "módulo genérico + título de webconferência")
    igual(guess_type("page", "Prova final"), "exam", "módulo genérico + prova")

    print("\n[5] Evento do calendário no formato do banco")
    quando = datetime(2026, 9, 10, 23, 59, tzinfo=TZ_BR)
    bruto = {
        "id": 42,
        "name": "Atividade 3 está marcado(a) para esta data",
        "timestart": int(quando.timestamp()),
        # `formattedtime` vem como HTML pronto e em 12h; usar ele daria "11:59 PM".
        "formattedtime": '<span class="dimmed_text">11:59 PM</span>',
        "description": "<p>Leia o <b>capítulo 2</b></p>",
        "course": {"id": 9, "fullname": "10275 - ENGENHARIA DE SOFTWARE - EAD54-12"},
        "modulename": "assign",
        "eventtype": "due",
        "url": "https://on.unoesc.edu.br/mod/assign/view.php?id=1",
    }
    eventos = MoodleClient.normalize_events([bruto, {"id": 43, "name": "sem data"}])
    igual(len(eventos), 1, "evento sem timestart é descartado")
    e = eventos[0]
    igual(e["date"], "2026-09-10", "a data sai do timestart, no fuso do Brasil")
    igual(e["time"], "23:59", "a hora vem do timestart, não do formattedtime")
    igual(e["description"], "Leia o capítulo 2", "a descrição vira texto puro")
    igual(e["subject"], "ENGENHARIA DE SOFTWARE", "a disciplina já vem limpa")
    igual(e["type"], "deadline", "o tipo sai do módulo")
    igual(e["course_id"], 9, "o course_id fica, é ele que liga evento e disciplina")

    print("\n[6] Identidade do evento")
    igual(event_key({"moodle_event_id": 42, "subject": "x", "date": "y", "title": "z"}),
          moodle_event_key(42), "com id do Moodle, a chave é o id")
    verificar(
        event_key({"subject": "MAT", "date": "2026-09-10", "title": "Prova"})
        == stable_event_key("MAT", "2026-09-10", "Prova"),
        "sem id, cai no hash de disciplina + data + título",
    )
    verificar(
        stable_event_key("MAT", "2026-09-10", "Prova")
        != stable_event_key("MAT", "2026-09-11", "Prova"),
        "datas diferentes dão chaves diferentes",
    )

    print("\n[7] Página da atividade (regex sobre o HTML do Moodle)")
    html = (
        '<div><h2>Atividade 3</h2><p>Enunciado da atividade.</p>'
        '<table class="generaltable">'
        '<tr><th>Status de envio</th><td>Enviado para avaliação</td></tr>'
        '<tr><th>Nota</th><td>-</td></tr>'
        '<tr><td>linha de uma célula só</td></tr>'
        '</table></div>'
    )
    status = MoodleClient._extract_status(html)
    igual(status, [{"label": "Status de envio", "value": "Enviado para avaliação"}],
          "só as linhas com rótulo e valor de verdade entram")
    igual(MoodleClient._extract_intro(html, "Atividade 3"), "Enunciado da atividade.",
          "o enunciado para antes da tabela e não repete o título")
    igual(MoodleClient._extract_status("<div>sem tabela</div>"), [],
          "página sem tabela devolve lista vazia, não erro")

    print("\n[8] Webconferência garimpada do texto da página")
    texto = (
        "WEBCONFERÊNCIA 1\nData: 05/05/2026\nHorário: 19h - 21h\n"
        "Lembre-se! É de suma importância que você participe da webconferência.\n"
    )
    webconfs = extract_webconferences(texto, "MAT", "https://on.unoesc.edu.br/c", 7)
    igual(len(webconfs), 1, "o texto-modelo sem data não vira evento")
    igual(webconfs[0]["date"], "2026-05-05", "a data anunciada é lida")
    igual(webconfs[0]["time"], "19:00", "o horário sai do “19h”")
    igual(webconfs[0]["moodle_event_id"], "webconf-7-1",
          "a chave é curso + número, porque não há evento no Moodle")

    print("\n[9] Texto das notificações")
    # Webconferência tem hora marcada e quem perde não recupera. Chamá-la de
    # "entrega" mandava o aluno olhar o lugar errado da agenda.
    webconf = [{"type": "webconference", "time": "19:30", "subject": "28743 - Eng. de Software"}]
    igual(push.resumo_do_dia(webconf)[0], "Webconferência hoje às 19:30",
          "webconferência não é anunciada como entrega")
    igual(push.vespera(webconf)[0], "Webconferência amanhã às 19:30",
          "a véspera muda só a palavra")

    prova = [{"type": "exam", "time": "19:00", "subject": "90112 - Farmacologia"},
             {"type": "deadline", "subject": "28743 - Eng. de Software"}]
    igual(push.resumo_do_dia(prova)[0], "Prova hoje às 19:00",
          "a prova encabeça o aviso, é o que não dá para remarcar")
    igual(push.resumo_do_dia(prova)[1], "Farmacologia · e mais 1 compromisso",
          "o resto do dia entra no corpo, sem sumir")

    igual(push.resumo_do_dia([{"type": "deadline", "subject": "31002 - Banco de Dados"}])[0],
          "Hoje: 1 entrega", "singular sem parêntese — é uma notificação, não um relatório")
    igual(push.resumo_do_dia([]), None, "dia vazio não vira notificação")

    igual(push.notas_novas([{"name": "90112 - Farmacologia", "final_grade": 85}])[1],
          "Farmacologia — 8,5", "a nota aparece na escala que o aluno lê")

    print("\n[10] Login: matrícula sozinha vale pelo e-mail inteiro")
    from app.moodle import normalizar_login

    igual(normalizar_login("294833"), "294833@unoesc.edu.br",
          "só o número vira o login completo")
    igual(normalizar_login(" 294833 "), "294833@unoesc.edu.br",
          "espaço colado não muda a conta")
    igual(normalizar_login("294833@UNOESC.edu.br"), "294833@unoesc.edu.br",
          "maiúscula não cria uma segunda conta")
    igual(normalizar_login("nome.sobrenome"), "nome.sobrenome",
          "login que não é número fica intacto — inventar domínio quebraria quem já entra")
    igual(normalizar_login("professor@unoesc.edu.br"), "professor@unoesc.edu.br",
          "quem já digitou o domínio passa direto")

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
