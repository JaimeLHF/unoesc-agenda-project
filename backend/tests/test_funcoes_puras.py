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

from app import assistant, grades, push
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

    # O bug de 01/09/2026: a página anunciava a Webconferência 1 duas vezes,
    # com datas diferentes. As duas viravam evento com a mesma chave, a
    # segunda sobrescrevia a primeira no banco com a data velha, e o disparo
    # de notificação anunciava "prazo antecipado" de três em três horas.
    repetido = (
        "WEBCONFERÊNCIA 1\nData: 02/09/2026\nHorário: 19h - 21h\n"
        "WEBCONFERÊNCIA 1\nData: 30/09/2026\nHorário: 19h - 21h\n"
    )
    dobrada = extract_webconferences(repetido, "MAT", "https://on.unoesc.edu.br/c", 7)
    igual(len(dobrada), 1, "a mesma webconferência anunciada duas vezes é uma só")
    igual(dobrada[0]["date"], "2026-09-02", "vale o primeiro anúncio da página")

    # "Data:" que aparece depois de outra menção a webconferência é do bloco
    # seguinte: casar com ele dava à Webconferência 1 a data da 2.
    cruzado = "WEBCONFERÊNCIA 1 (gravada)\nWEBCONFERÊNCIA 2\nData: 30/09/2026\n"
    misturada = extract_webconferences(cruzado, "MAT", "https://on.unoesc.edu.br/c", 7)
    igual([e["moodle_event_id"] for e in misturada], ["webconf-7-2"],
          "a data não pula de um bloco para o outro")

    print("\n[8.1] Quanto falta para passar")
    # A conta que o aluno faz na calculadora do celular. Errar para menos aqui
    # faz alguém relaxar na prova que decide a aprovação, e ninguém percebe:
    # o número parece plausível.
    meio_do_semestre = [
        {"nome": "AV1", "nota": 6.0, "peso": 25.0, "maximo": 10},
        {"nome": "AV2", "nota": 9.0, "peso": 50.0, "maximo": 10},
        {"nome": "AV3", "nota": None, "peso": 25.0, "maximo": 10},
    ]
    previsao = grades.prever(meio_do_semestre)
    igual(previsao["atual"], 6.0, "a média parcial usa o peso de cada avaliação")
    igual(previsao["precisa"], 4.0, "e devolve quanto falta na que resta")
    igual(previsao["situacao"], "precisa", "situação de quem ainda depende da última")

    garantido = grades.prever([
        {"nome": "AV1", "nota": 10.0, "peso": 80.0, "maximo": 10},
        {"nome": "AV2", "nota": None, "peso": 20.0, "maximo": 10},
    ])
    igual(garantido["situacao"], "garantido", "8,0 de 10 com 20% em jogo já fecha a média")
    verificar("Aprovação garantida" in (grades.frase(garantido) or ""),
              "e a frase diz isso sem o aluno abrir a calculadora")

    impossivel = grades.prever([
        {"nome": "AV1", "nota": 2.0, "peso": 80.0, "maximo": 10},
        {"nome": "AV2", "nota": None, "peso": 20.0, "maximo": 10},
    ])
    igual(impossivel["situacao"], "impossivel",
          "nem 10 nos 20% restantes chega a 7,0 — e a tela precisa dizer")

    # O caso que mais aparece: o Moodle só dá peso ao item depois de lançar a
    # nota, então no meio do semestre os pesos não fecham. Aqui a resposta
    # certa é "não dá para saber", nunca um número.
    sem_peso = grades.prever([
        {"nome": "AV1", "nota": 9.0, "peso": 20.0, "maximo": 10},
        {"nome": "AV2", "nota": None, "peso": None, "maximo": 10},
    ])
    igual(sem_peso["situacao"], "sem_base", "pesos que não fecham 100% não viram previsão")
    igual(grades.frase(sem_peso), None, "e sem base a tela não escreve nada")
    igual(grades.prever([])["situacao"], "sem_base", "boletim vazio não vira conta")

    # Nota que não foi lançada nunca conta como zero: isso diria "reprovado"
    # para quem ainda não fez a prova.
    igual(grades.prever([
        {"nome": "AV1", "nota": None, "peso": 100.0, "maximo": 10},
    ])["atual"], None, "avaliação sem nota não derruba a média para zero")

    # Escala diferente de 0–10 (45 de 50) tem de virar 9,0 antes de pesar.
    igual(grades.prever([
        {"nome": "AV1", "nota": 45.0, "peso": 100.0, "maximo": 50},
    ])["atual"], 9.0, "a nota é convertida para a escala 0–10 pelo máximo do item")

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

    # O lembrete da tarde: o resumo das 7h já saiu da tela quando a
    # webconferência das 19h chega.
    proximo = [{"type": "webconference", "title": "Webconferência 1", "time": "19:00",
                "subject": "24728 - Empreendedorismo e Inovação"}]
    igual(push.lembrete(proximo, 120)[1],
          "Webconferência 1 — Empreendedorismo e Inovação · 19:00",
          "o corpo diz qual é o compromisso e a que horas")
    igual(push.lembrete(proximo + [{"type": "deadline", "title": "AV2",
                                     "subject": "31002 - Banco de Dados"}], 120)[0],
          "Webconferência em 2h", "o título diz quanto falta, não a data")
    igual(push.lembrete([{"type": "exam", "title": "Prova 1", "time": "19:00",
                          "subject": "90112 - Farmacologia"}], 45)[0],
          "Prova em 45 min", "abaixo de uma hora e meia a conta é em minutos")
    igual(push.lembrete([], 0), None, "tarde sem compromisso não vira notificação")

    # Nota perdida por esquecimento é a única que não se recupera estudando.
    igual(push.ultima_chamada([{"title": "Atividade Avaliativa 1", "time": "23:59",
                                "subject": "28743 - Desenvolvimento Mobile"}])[0],
          "Última chamada — 23:59", "a hora do fim do prazo vai no título")
    igual(push.ultima_chamada([])[0] if push.ultima_chamada([]) else None, None,
          "sem entrega pendente não sai nada às 21h")

    igual(push.abriu_para_envio([{"title": "Tarefa 2",
                                  "subject": "31002 - Banco de Dados"}])[0],
          "Abriu para envio", "a atividade que passou a aceitar envio é notícia")

    # O empurrãozinho de quem sumiu. Não tem fato por trás, então o que
    # sustenta é o repertório: frase repetida vira paisagem, e frase que
    # promete tela inexistente custa a confiança de quem abriu.
    verificar(len(push.LEMBRETES_DE_HABITO) >= 10,
              "há repertório suficiente para não repetir frase no mesmo mês")
    verificar(len({t for t, _, _ in push.LEMBRETES_DE_HABITO})
              == len(push.LEMBRETES_DE_HABITO), "nenhum título de hábito repetido")
    verificar(all(t and c and u.startswith("/")
                  for t, c, u in push.LEMBRETES_DE_HABITO),
              "toda frase tem título, corpo e um destino dentro do app")
    verificar(all(len(t) <= 40 for t, _, _ in push.LEMBRETES_DE_HABITO),
              "título curto o bastante para caber na tela bloqueada")
    igual(push.habito(len(push.LEMBRETES_DE_HABITO)), push.habito(0),
          "a rotação dá a volta em vez de estourar a lista")

    igual(push.notas_novas([{"name": "90112 - Farmacologia", "final_grade": 85}])[1],
          "Farmacologia — 8,5", "a nota aparece na escala que o aluno lê")

    # O total da disciplina só existe quando o Moodle já deu peso a tudo; no
    # meio do semestre a única notícia é a nota da avaliação. Foi o que faltou
    # quando a UNOESC mandou o e-mail de nota parcial e o app ficou calado.
    item = [{"subject": "28743 - Desenvolvimento Mobile",
             "name": "Tarefa ATIVIDADE AVALIATIVA 1", "grade": 9.0, "max": 10}]
    igual(push.notas_de_item(item)[1],
          "Desenvolvimento Mobile · ATIVIDADE AVALIATIVA 1 — 9,0",
          "o aviso diz qual avaliação saiu, não só a disciplina")
    igual(push.notas_de_item([{**item[0], "max": 50, "grade": 45}])[1],
          "Desenvolvimento Mobile · ATIVIDADE AVALIATIVA 1 — 45,0/50",
          "escala que não é 0–10 mostra o total, senão 45 pareceria acima da média")
    igual(push.notas_de_item([])[0] if push.notas_de_item([]) else None, None,
          "boletim sem novidade não vira notificação")
    igual(push.notas_de_item(item + [{**item[0], "name": "Tarefa AVALIATIVA 2"}])[0],
          "Saíram 2 notas", "duas notas viram um aviso só")

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

    # -- prazo lido na página da atividade -------------------------------
    #
    # Estas frases são o que a página do Moodle mostra quando o professor
    # publicou a avaliação sem cadastrar a data no calendário. Ler errado aqui
    # coloca um prazo inventado na agenda de alguém — por isso teste puro.
    print("\n▶ prazo na página da atividade")
    from app.moodle import prazo_no_texto, cmid_da_url

    igual(prazo_no_texto("Aberto: quarta-feira, 6 agosto 2026, 00:00 "
                         "Vencimento: domingo, 6 setembro 2026, 23:59"),
          ("2026-09-06", "23:59"),
          "vencimento por extenso vira data e hora")
    igual(prazo_no_texto("Este questionário será encerrado em terça-feira, "
                         "9 de setembro de 2026 às 22:00"),
          ("2026-09-09", "22:00"),
          "questionário anuncia o fechamento em outra forma")
    igual(prazo_no_texto("Data de entrega 06/09/2026, 23:59"),
          ("2026-09-06", "23:59"),
          "data numérica também conta")
    igual(prazo_no_texto("Aberto: quarta-feira, 6 agosto 2026, 00:00"),
          None,
          "data de abertura não é prazo — viraria um evento no dia em que a "
          "atividade nasceu")
    igual(prazo_no_texto("Atividade de Resgate Data de entrega: sexta-feira, "
                         "11 setembro 2026, 23:59 Adicionar tópico de discussão"),
          ("2026-09-11", "23:59"),
          "fórum avaliativo (hsuforum) anuncia entrega como qualquer tarefa")
    igual(prazo_no_texto("Tira-dúvidas Adicionar tópico de discussão"), None,
          "fórum sem prazo não vira compromisso")
    igual(prazo_no_texto("Última modificação: 12 agosto 2026"), None,
          "data solta na página não vira prazo")
    igual(prazo_no_texto("Vencimento: 31 fevereiro 2026"), None,
          "data impossível é descartada em vez de virar evento errado")
    igual(prazo_no_texto(""), None, "página vazia não inventa prazo")

    igual(cmid_da_url("https://moodle.unoesc.edu.br/mod/assign/view.php?id=123&action=view"),
          "123", "cmid sai do link da tarefa")
    igual(cmid_da_url("https://moodle.unoesc.edu.br/mod/quiz/view.php?id=456"),
          "456", "cmid sai do link do questionário")
    igual(cmid_da_url("https://moodle.unoesc.edu.br/course/view.php?id=9"), None,
          "link de curso não é atividade — casar aqui esconderia a atividade 9")

    # ---- Lumi: quando o enunciado entra, e quando a pergunta é de graça ----
    #
    # As duas coisas quebram caladas. Uma detecção frouxa manda o app abrir o
    # Moodle a cada "e aí?" — espera na tela por nada; uma frouxa demais no
    # outro sentido deixa o aluno ouvindo "não tenho acesso", que foi a queixa
    # de 29/08/2026. E o desconto injusto do saldo só apareceria no contador.
    igual(assistant.quer_conteudo("Sobre o que é exatamente a atividade de "
                                  "desenvolvimento mobile?"), True,
          "pergunta de conteúdo é reconhecida")
    igual(assistant.quer_conteudo("O que preciso fazer na avaliativa 2?"), True,
          "'o que preciso fazer' pede o enunciado")
    igual(assistant.quer_conteudo("me explica essa atividade"), True,
          "'explica' pede o enunciado")
    igual(assistant.quer_conteudo("O que preciso entregar até o dia 06/09?"), True,
          "pergunta de agenda com 'o que preciso entregar' também abre o "
          "enunciado — custa uma requisição e responde melhor")
    igual(assistant.quer_conteudo("Quais são meus prazos desta semana?"), False,
          "pergunta de agenda pura não vai ao Moodle")
    igual(assistant.quer_conteudo("Como divido meu tempo até sexta?"), False,
          "planejamento não precisa de enunciado")

    class _Ev:
        def __init__(self, title, subject, date, url="http://x"):
            self.title, self.subject, self.date, self.url = title, subject, date, url

    eventos = [
        _Ev("Entrega da Atividade Avaliativa 2", "DESENVOLVIMENTO MOBILE", "2026-09-06"),
        _Ev("Entrega da Atividade Avaliativa 2",
            "REDES DE COMPUTADORES E SISTEMAS DISTRIBUÍDOS", "2026-09-06"),
    ]
    escolhido = assistant.escolher_atividade(
        "Sobre o que é exatamente a atividade de desenvolvimento mobile?", eventos)
    igual(escolhido and escolhido.subject, "DESENVOLVIMENTO MOBILE",
          "a disciplina citada escolhe entre duas entregas de mesmo nome")
    escolhido = assistant.escolher_atividade(
        "e essa atividade, sobre o que é?", eventos,
        anteriores="quero saber de redes de computadores")
    igual(escolhido and escolhido.subject,
          "REDES DE COMPUTADORES E SISTEMAS DISTRIBUÍDOS",
          "'essa' aponta para o que foi dito antes na conversa")
    igual(assistant.escolher_atividade("bom dia", eventos), None,
          "pergunta sem nenhuma pista não abre atividade nenhuma")
    igual(assistant.escolher_atividade("qualquer coisa", []), None,
          "agenda vazia não escolhe atividade")

    igual(assistant.formatar_enunciado(eventos[0], {"intro": ""}), "",
          "atividade sem enunciado não vira bloco vazio no prompt")
    longo = assistant.formatar_enunciado(eventos[0], {"intro": "x" * 9000}, limite=100)
    igual(len(longo) < 400, True, "enunciado gigante é cortado")

    igual(assistant.separar_marca("SEM_AJUDA\nNão tenho essa informação."),
          ("Não tenho essa informação.", False),
          "resposta marcada sai limpa e não desconta a pergunta")
    igual(assistant.separar_marca("06/09 às 23:59: entrega de Mobile."),
          ("06/09 às 23:59: entrega de Mobile.", True),
          "resposta útil desconta normalmente")
    igual(assistant.separar_marca("SEM_AJUDA"), ("Não consegui ajudar com isso.", False),
          "marca sozinha ainda mostra alguma frase ao aluno")

    prompt = assistant.build_system_prompt("- 06/09 | MOBILE | entrega: AV2",
                                           "Enunciado: faça um app.")
    igual("Nunca produza o trabalho" in prompt, True,
          "com enunciado à mão, a regra de não resolver o trabalho está no prompt")

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
