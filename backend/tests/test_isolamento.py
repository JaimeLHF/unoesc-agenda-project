"""
Critério de aceite do multi-tenant: dois alunos logados ao mesmo tempo não
enxergam nada um do outro.

Roda sem pytest e sem rede — o `MoodleClient` é substituído por um dublê:

    cd backend && python -m tests.test_isolamento

Sai com código 1 na primeira falha. É o teste que decide se a versão pública
pode ir ao ar; qualquer mudança em `repository.py` deveria passar por aqui.
"""

import os
import sys
import tempfile
from pathlib import Path

# Precisa vir antes de importar `app.*`: o módulo do banco lê o caminho no
# import e um teste jamais deve escrever no agenda.db de verdade.
_tmp = Path(tempfile.mkdtemp(prefix="agenda-teste-"))
os.environ["DATABASE_PATH"] = str(_tmp / "teste.db")
os.environ["SESSION_SECRET"] = "segredo-de-teste-nao-usar-em-producao"
os.environ["APP_ENV"] = "development"
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
# Par VAPID de teste: liga os endpoints de notificação sem que nada saia daqui
# — o teste nunca chama o serviço de push, só grava e lê inscrições.
os.environ["VAPID_PUBLIC_KEY"] = (
    "BFk0P8FBPpy78uNynZeSv6xWEIZka_sDTW6cr4ZUMB8b4tm-KABtzKGa_JhDMUwGjlS6W_iGdPaDpGOEomGfi-Q"
)
os.environ["VAPID_PRIVATE_KEY"] = "i7gmNRsB8Ivs-sp9tkaT68z14PUchSP9nAZRQzjWZBU"
os.environ.pop("PUSH_CRON_TOKEN", None)
# O painel do dono só existe quando este secret existe — ver app/admin.py.
os.environ.pop("ADMIN_USERNAMES", None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app import ratelimit  # noqa: E402

# Credenciais aceitas pelo Moodle falso, e a agenda que cada uma devolve.
CONTAS = {
    "aluno.a@unoesc.edu.br": "senha-a",
    "aluno.b@unoesc.edu.br": "senha-b",
    # Matrícula numérica: o caso em que o aluno digita só o número e o backend
    # completa o domínio antes de falar com o Moodle.
    "123456@unoesc.edu.br": "senha-c",
}

AGENDAS = {
    "aluno.a@unoesc.edu.br": {
        "subjects": [{
            "id": "1", "name": "Cálculo I", "content": "",
            "dof": "CAL1", "course_id": 101, "course_url": "https://on.unoesc.edu.br/course/view.php?id=101",
            "activities": [{"cmid": "111", "name": "Plano de ensino",
                            "modname": "resource", "url": "/mod/resource/view.php?id=111"}],
        }],
        "calendar_events": [{
            "id": "ev-a", "moodle_event_id": 9001, "title": "Prova 1", "date": "2099-05-10",
            "time": "19:00", "description": "", "subject": "Cálculo I",
            "type": "exam", "source": "moodle_calendar", "url": None,
        }],
    },
    "aluno.b@unoesc.edu.br": {
        "subjects": [{
            "id": "2", "name": "Redes de Computadores", "content": "",
            "dof": "RED1", "course_id": 202, "course_url": "https://on.unoesc.edu.br/course/view.php?id=202",
            "activities": [{"cmid": "222", "name": "Regras do trabalho",
                            "modname": "resource", "url": "/mod/resource/view.php?id=222"}],
        }],
        "calendar_events": [{
            "id": "ev-b", "moodle_event_id": 9002, "title": "Trabalho de Redes", "date": "2099-06-20",
            "time": None, "description": "", "subject": "Redes de Computadores",
            "type": "deadline", "source": "moodle_calendar", "url": None,
        }],
    },
}


PERFIS = {
    "aluno.a@unoesc.edu.br": {
        "moodle_id": 1, "fullname": "Aluno A", "firstname": "Aluno", "lastname": "A",
        "username": "aluno.a", "email": "aluno.a@unoesc.edu.br", "department": "",
        "institution": "", "city": "", "country": "BR", "timezone": "America/Sao_Paulo",
        "first_access": None, "last_access": None, "avatar": None,
    },
    "aluno.b@unoesc.edu.br": {
        "moodle_id": 2, "fullname": "Aluno B", "firstname": "Aluno", "lastname": "B",
        "username": "aluno.b", "email": "aluno.b@unoesc.edu.br", "department": "",
        "institution": "", "city": "", "country": "BR", "timezone": "America/Sao_Paulo",
        "first_access": None, "last_access": None, "avatar": None,
    },
}


# Liga a segunda visita ao Moodle: o professor de A adiou a prova e publicou um
# arquivo. É o que faz nascer "prazo alterado" e "material novo" — os dois
# avisos são dado do aluno e precisam ficar dentro da conta dele.
SEGUNDA_RODADA = {"ativa": False}

PROVA_ADIADA_PARA = "2099-05-17"
MATERIAL_NOVO_DE_A = "Slides da aula 9"
NOTA_LANCADA_PARA_A = 87.5


class MoodleFalso:
    """Dublê do `MoodleClient`: valida credencial e devolve agenda fixa."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, username, password):
        if CONTAS.get(username) != password:
            raise PermissionError("Usuário ou senha inválidos.")
        self._username = username

    def profile(self):
        """Cadastro do aluno que logou neste cliente — nunca de outro."""
        return dict(PERFIS[self._username])

    def run(self, username, password):
        self.login(username, password)
        # Cópia profunda rasa: `upsert_events` escreve `stable_key` no dict.
        agenda = AGENDAS[username]
        subjects = [dict(s) for s in agenda["subjects"]]
        eventos = [dict(e) for e in agenda["calendar_events"]]

        if SEGUNDA_RODADA["ativa"] and username == "aluno.a@unoesc.edu.br":
            eventos[0]["date"] = PROVA_ADIADA_PARA
            subjects[0]["activities"] = subjects[0]["activities"] + [{
                "cmid": "555", "name": MATERIAL_NOVO_DE_A,
                "modname": "resource", "url": "/mod/resource/view.php?id=555",
            }]
            subjects[0]["final_grade"] = NOTA_LANCADA_PARA_A

        return {"subjects": subjects, "calendar_events": eventos}


main.MoodleClient = MoodleFalso

falhas: list[str] = []


def verificar(condicao: bool, descricao: str) -> None:
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        falhas.append(descricao)


def entrar(client: TestClient, username: str) -> str:
    resp = client.post(
        "/api/login", json={"username": username, "password": CONTAS[username]}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def entrar_com(client: TestClient, username: str, password: str) -> str:
    """Login com o texto exatamente como o aluno digitou."""
    resp = client.post("/api/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main_teste() -> int:
    with TestClient(main.app) as client:
        print("\n[1] Dois alunos, duas agendas")
        token_a = entrar(client, "aluno.a@unoesc.edu.br")
        token_b = entrar(client, "aluno.b@unoesc.edu.br")
        verificar(token_a != token_b, "tokens diferentes para alunos diferentes")

        scrape_a = client.post("/api/scrape", headers=auth(token_a))
        scrape_b = client.post("/api/scrape", headers=auth(token_b))
        # Sem isto o teste só olhava o /api/cache, e um erro ao montar a
        # resposta do scrape passava calado — os dados já tinham sido gravados.
        verificar(
            scrape_a.status_code == 200 and scrape_b.status_code == 200,
            f"o scrape responde 200 para os dois ({scrape_a.status_code}/{scrape_b.status_code})",
        )

        cache_a = client.get("/api/cache", headers=auth(token_a)).json()
        cache_b = client.get("/api/cache", headers=auth(token_b)).json()

        disciplinas_a = {s["name"] for s in cache_a["subjects"]}
        disciplinas_b = {s["name"] for s in cache_b["subjects"]}
        verificar(disciplinas_a == {"Cálculo I"}, f"A só vê as disciplinas dele ({disciplinas_a})")
        verificar(
            disciplinas_b == {"Redes de Computadores"},
            f"B só vê as disciplinas dele ({disciplinas_b})",
        )

        titulos_a = {e["title"] for e in cache_a["events"]}
        titulos_b = {e["title"] for e in cache_b["events"]}
        verificar(titulos_a == {"Prova 1"}, f"A só vê os eventos dele ({titulos_a})")
        verificar(titulos_b == {"Trabalho de Redes"}, f"B só vê os eventos dele ({titulos_b})")

        print("\n[2] Concluídos são de quem marcou")
        chave_a = cache_a["events"][0]["stable_key"]
        client.post("/api/done-events", json={"stable_key": chave_a}, headers=auth(token_a))
        done_a = client.get("/api/done-events", headers=auth(token_a)).json()["done_keys"]
        done_b = client.get("/api/done-events", headers=auth(token_b)).json()["done_keys"]
        verificar(done_a == [chave_a], "A vê o que marcou")
        verificar(done_b == [], "B não vê a marcação de A")

        print("\n[2.1] Prazo alterado e material novo ficam na conta de quem viu")
        SEGUNDA_RODADA["ativa"] = True
        client.post("/api/scrape", headers=auth(token_a))
        client.post("/api/scrape", headers=auth(token_b))
        SEGUNDA_RODADA["ativa"] = False

        cache_a = client.get("/api/cache", headers=auth(token_a)).json()
        cache_b = client.get("/api/cache", headers=auth(token_b)).json()
        evento_a = cache_a["events"][0]
        evento_b = cache_b["events"][0]

        verificar(
            evento_a["date"] == PROVA_ADIADA_PARA
            and evento_a["previous_date"] == "2099-05-10",
            "A vê a data anterior da própria prova",
        )
        verificar(evento_b["previous_date"] is None, "B não herda o aviso de mudança de A")

        novos_a = {m["name"] for m in cache_a["subjects"][0]["new_materials"]}
        novos_b = {m["name"] for m in cache_b["subjects"][0]["new_materials"]}
        verificar(novos_a == {MATERIAL_NOVO_DE_A}, f"A vê só o material novo dele ({novos_a})")
        verificar(
            "Plano de ensino" not in novos_a,
            "o que já estava na sala no primeiro acesso não conta como novidade",
        )
        verificar(novos_b == set(), f"B não vê o material que apareceu na sala de A ({novos_b})")

        disciplina_a = cache_a["subjects"][0]
        disciplina_b = cache_b["subjects"][0]
        verificar(
            disciplina_a["grade_changed"] is True
            and disciplina_a["final_grade"] == NOTA_LANCADA_PARA_A,
            "A vê que saiu nota na disciplina dele",
        )
        verificar(
            disciplina_a["previous_grade"] is None,
            "a primeira nota da disciplina não inventa uma nota anterior",
        )
        verificar(
            disciplina_b["grade_changed"] is False,
            "B não recebe o aviso de nota de A",
        )

        # O relatório de notas do Moodle já respondeu `servicenotavailable`
        # nesta instância. Quando ele falha, a nota chega nula — e sobrescrever
        # apagaria em silêncio a nota que o aluno já tinha visto.
        client.post("/api/scrape", headers=auth(token_a))
        depois = client.get("/api/cache", headers=auth(token_a)).json()["subjects"][0]
        verificar(
            depois["final_grade"] == NOTA_LANCADA_PARA_A,
            f"scrape sem nota não apaga a nota guardada ({depois['final_grade']})",
        )

        print("\n[3] Nenhum endpoint de dados responde sem sessão")
        sem_sessao = [
            ("get", "/api/cache", None),
            ("get", "/api/done-events", None),
            ("post", "/api/done-events", {"stable_key": chave_a}),
            ("post", "/api/scrape", None),
            ("delete", "/api/cache", None),
            ("get", "/api/me", None),
            ("post", "/api/open-course", {"subject_name": "Cálculo I"}),
            ("post", "/api/assistant", {"messages": [{"role": "user", "content": "oi"}]}),
            ("delete", "/api/account", None),
            ("get", "/api/activity/moodle:1", None),
            ("get", "/api/profile", None),
            ("get", "/api/submission/moodle:1", None),
            ("get", "/api/calendar-feed", None),
            ("post", "/api/calendar-feed/reset", None),
            ("post", "/api/grades", {"subject_name": "Cálculo I"}),
            ("get", "/api/push/config", None),
            ("post", "/api/push/subscribe", {
                "endpoint": "https://push.exemplo/x", "keys": {"p256dh": "p", "auth": "a"},
            }),
            ("post", "/api/push/test", None),
        ]
        for metodo, rota, corpo in sem_sessao:
            resp = getattr(client, metodo)(rota, json=corpo) if corpo else getattr(client, metodo)(rota)
            verificar(resp.status_code == 401, f"{metodo.upper()} {rota} → 401 sem token")

        print("\n[3.1] Calendário assinável leva só a agenda do dono")
        # O `.ics` é buscado pelo servidor do Google, que não carrega token de
        # sessão: a chave da URL é a credencial inteira. Se ela alcançasse a
        # agenda de outro aluno, bastaria um endereço vazado.
        url_a = client.get("/api/calendar-feed", headers=auth(token_a)).json()["url"]
        url_b = client.get("/api/calendar-feed", headers=auth(token_b)).json()["url"]
        verificar(url_a != url_b, "cada aluno tem sua própria chave de calendário")

        caminho_a = "/calendario/" + url_a.split("/calendario/")[1]
        caminho_b = "/calendario/" + url_b.split("/calendario/")[1]
        ics_a = client.get(caminho_a)
        ics_b = client.get(caminho_b)
        verificar(ics_a.status_code == 200, "o calendário do dono responde sem sessão")
        verificar("Prova 1" in ics_a.text, "o calendário de A traz o evento de A")
        verificar("Trabalho de Redes" not in ics_a.text, "o calendário de A não traz evento de B")
        verificar("Trabalho de Redes" in ics_b.text, "o calendário de B traz o evento de B")
        verificar(
            client.get("/calendario/chave-inventada.ics").status_code == 404,
            "chave inválida não devolve calendário",
        )

        # Trocar a chave precisa invalidar a antiga na hora — é o botão de
        # "vazou o endereço, corta o acesso".
        nova = client.post("/api/calendar-feed/reset", headers=auth(token_a)).json()["url"]
        verificar(nova != url_a, "reset gera uma chave nova")
        verificar(client.get(caminho_a).status_code == 404, "a chave antiga para de responder")

        print("\n[4] Token de A não alcança dados de B")
        # `open-course` sem `target_url` resolve pelo cache do dono do token.
        resp = client.post(
            "/api/open-course",
            json={"subject_name": "Redes de Computadores"},
            headers=auth(token_a),
        )
        verificar(resp.status_code == 404, "A não consegue abrir disciplina de B")

        # O boletim recebe o nome da disciplina no corpo — é o mesmo formato do
        # open-course e, portanto, o mesmo caminho por onde um nome alheio
        # tentaria entrar.
        verificar(
            client.post(
                "/api/grades",
                json={"subject_name": "Redes de Computadores"},
                headers=auth(token_a),
            ).status_code == 404,
            "A não lê o boletim da disciplina de B",
        )

        # A página de atividade tem endereço próprio e compartilhável. A busca
        # é por (user_id, stable_key), então o link de B abre 404 para A — é o
        # que impede um link compartilhado de virar vazamento.
        chave_de_b = client.get("/api/cache", headers=auth(token_b)).json()["events"][0][
            "stable_key"
        ]
        resp = client.get(f"/api/activity/{chave_de_b}", headers=auth(token_a))
        verificar(resp.status_code == 404, "A não abre a atividade de B pelo link dela")

        resp = client.get(f"/api/activity/{chave_de_b}", headers=auth(token_b))
        verificar(resp.status_code == 200, "B abre a própria atividade")

        # Envio de tarefa mexe no Moodle de quem envia. A chave vem da URL,
        # então é o primeiro lugar onde um link de outro aluno tentaria entrar.
        verificar(
            client.get(f"/api/submission/{chave_de_b}", headers=auth(token_a)).status_code == 404,
            "A não abre o envio da tarefa de B",
        )
        verificar(
            client.post(
                f"/api/submission/{chave_de_b}",
                data={"online_text": "tentativa"},
                headers=auth(token_a),
            ).status_code == 404,
            "A não consegue enviar na tarefa de B",
        )
        verificar(
            client.post(f"/api/submission/{chave_de_b}",
                        data={"online_text": "sem sessão"}).status_code == 401,
            "POST /api/submission → 401 sem token",
        )

        # O perfil é o endpoint que mistura duas fontes — cadastro do Moodle e
        # contagens do banco. As duas precisam vir da mesma conta.
        perfil_a = client.get("/api/profile", headers=auth(token_a)).json()
        perfil_b = client.get("/api/profile", headers=auth(token_b)).json()
        verificar(
            perfil_a["moodle"]["email"] == "aluno.a@unoesc.edu.br"
            and perfil_b["moodle"]["email"] == "aluno.b@unoesc.edu.br",
            "cada perfil traz o cadastro do próprio aluno",
        )
        verificar(
            perfil_a["stats"]["subjects"] == 1 and perfil_a["stats"]["events_total"] == 1,
            "contagens do perfil de A só somam a agenda de A",
        )
        verificar(
            perfil_a["stats"]["events_done"] == 1 and perfil_b["stats"]["events_done"] == 0,
            "concluído de A não aparece nas contagens de B",
        )
        verificar(
            perfil_b["stats"]["next_event_title"] == "Trabalho de Redes",
            "próximo evento do perfil é o da agenda do próprio aluno",
        )

        print("\n[4.1] Notificação: cada aparelho pertence a uma conta só")
        # A senha do Moodle fica cifrada junto da inscrição — é o que permite
        # avisar "saiu nota" com o app fechado. Um endpoint alcançável pela
        # conta errada entregaria os avisos de um aluno no celular do outro.
        inscricao_a = {
            "endpoint": "https://push.exemplo/aluno-a",
            "keys": {"p256dh": "chave-publica-a", "auth": "auth-a"},
        }
        inscricao_b = {
            "endpoint": "https://push.exemplo/aluno-b",
            "keys": {"p256dh": "chave-publica-b", "auth": "auth-b"},
        }
        resp_a = client.post("/api/push/subscribe", json=inscricao_a, headers=auth(token_a))
        resp_b = client.post("/api/push/subscribe", json=inscricao_b, headers=auth(token_b))
        verificar(
            resp_a.status_code == 200 and resp_a.json()["devices"] == 1,
            "A inscreve o aparelho dele",
        )
        verificar(
            resp_b.status_code == 200 and resp_b.json()["devices"] == 1,
            "B inscreve o aparelho dele",
        )

        # Desinscrever pelo endpoint do vizinho não pode desligar o vizinho.
        client.request(
            "DELETE", "/api/push/subscribe",
            json={"endpoint": inscricao_b["endpoint"]}, headers=auth(token_a),
        )
        verificar(
            client.get("/api/push/config", headers=auth(token_b)).json()["devices"] == 1,
            "A não desliga a notificação de B",
        )

        from app.database import PushSubscription, SessionLocal as _SL
        with _SL() as _db:
            senhas = [i.password_enc for i in _db.query(PushSubscription).all()]
        verificar(
            all(s_ and "senha-" not in s_ for s_ in senhas),
            "a senha guardada na inscrição está cifrada, não em claro",
        )

        # Sem PUSH_CRON_TOKEN o disparo externo não existe. 404 e não 401: um
        # 401 confirmaria que há ali um botão de "notifique todo mundo agora".
        verificar(
            client.post("/api/push/run", headers={"X-Cron-Token": "chute"}).status_code == 404,
            "POST /api/push/run → 404 sem token de cron configurado",
        )

        print("\n[5] Limpar cache não atinge o vizinho")
        client.delete("/api/cache", headers=auth(token_a))
        cache_b_depois = client.get("/api/cache", headers=auth(token_b)).json()
        verificar(len(cache_b_depois["events"]) == 1, "B mantém os eventos após A limpar o cache")
        verificar(
            client.get("/api/cache", headers=auth(token_a)).status_code == 401,
            "sessão de A cai ao limpar o próprio cache",
        )

        print("\n[6] Rate limit de login")
        ratelimit.reset("aluno.c@unoesc.edu.br")
        codigos = [
            client.post(
                "/api/login",
                json={"username": "aluno.c@unoesc.edu.br", "password": "errada"},
            ).status_code
            for _ in range(ratelimit.MAX_ATTEMPTS + 1)
        ]
        verificar(
            codigos[:ratelimit.MAX_ATTEMPTS] == [401] * ratelimit.MAX_ATTEMPTS,
            f"as {ratelimit.MAX_ATTEMPTS} primeiras tentativas erradas dão 401",
        )
        verificar(codigos[-1] == 429, "a tentativa seguinte é bloqueada com 429")

        print("\n[7] Sessão persiste fora do processo")
        from app import session as app_session
        from app.database import AppSession, SessionLocal

        with SessionLocal() as db:
            gravadas = db.query(AppSession).count()
        verificar(gravadas > 0, "sessões estão no banco, não em memória")
        sessao = app_session.get(token_b)
        verificar(sessao is not None and sessao.username == "aluno.b@unoesc.edu.br",
                  "token de B resolve para a conta certa")

        print("\n[8] Excluir conta apaga tudo")
        client.delete("/api/account", headers=auth(token_b))
        token_b2 = entrar(client, "aluno.b@unoesc.edu.br")
        cache_b2 = client.get("/api/cache", headers=auth(token_b2)).json()
        verificar(cache_b2["events"] == [], "conta recriada volta vazia")
        verificar(cache_b2["done_keys"] == [], "marcações antigas não voltam")
        verificar(
            client.get("/api/push/config", headers=auth(token_b2)).json()["devices"] == 0,
            "excluir a conta apaga a inscrição de notificação e a senha nela",
        )

        print("\n[9] Matrícula sozinha é a mesma conta do e-mail completo")
        # Antes de `normalizar_login`, quem entrasse das duas formas ganhava
        # duas contas — duas agendas e duas inscrições de notificação, sem
        # nenhum sinal na tela. Aconteceu em produção.
        token_curto = entrar_com(client, "123456", "senha-c")
        me_curto = client.get("/api/me", headers=auth(token_curto)).json()
        verificar(
            me_curto["username"] == "123456@unoesc.edu.br",
            "entrar com a matrícula sozinha grava o login completo",
        )
        token_longo = entrar_com(client, "123456@unoesc.edu.br", "senha-c")
        me_longo = client.get("/api/me", headers=auth(token_longo)).json()
        verificar(
            me_longo["username"] == me_curto["username"],
            "as duas formas de digitar caem na mesma conta",
        )
        verificar(
            entrar_com(client, "  123456  ", "senha-c") is not None,
            "espaço em volta da matrícula não impede o login",
        )

        from app.database import SessionLocal as _Sessao, User as _User
        with _Sessao() as db:
            contas_123 = db.query(_User).filter(
                _User.moodle_username.like("123456%")
            ).count()
        verificar(contas_123 == 1, "não nasceu uma segunda conta para a mesma matrícula")

        print("\n[10] Painel do dono")
        token_a2 = entrar(client, "aluno.a@unoesc.edu.br")
        token_b3 = entrar(client, "aluno.b@unoesc.edu.br")

        # Sem o secret, a rota não existe para ninguém — nem para quem seria
        # o dono. É o estado de qualquer instalação que não pediu painel.
        verificar(
            client.get("/api/admin/panorama", headers=auth(token_a2)).status_code == 404,
            "sem ADMIN_USERNAMES o painel responde 404 até para o dono",
        )
        verificar(
            client.get("/api/me", headers=auth(token_a2)).json()["is_admin"] is False,
            "sem o secret ninguém é anunciado como admin",
        )

        os.environ["ADMIN_USERNAMES"] = "aluno.a"
        try:
            resposta = client.get("/api/admin/panorama", headers=auth(token_a2))
            verificar(resposta.status_code == 200, "o dono abre o painel")
            painel = resposta.json()
            usuarios = {c["username"] for c in painel["contas"]}
            verificar(
                {"aluno.a@unoesc.edu.br", "aluno.b@unoesc.edu.br"} <= usuarios,
                "o painel lista todas as contas — é o único endpoint que faz isso",
            )
            verificar(
                client.get("/api/me", headers=auth(token_a2)).json()["is_admin"] is True,
                "o dono é anunciado como admin para o frontend desenhar o link",
            )

            # O nome não vem do login (que é matrícula) nem do banco: ele chega
            # quando o aluno abre o app, e é o /api/profile que o guarda.
            sem_nome = {c["username"]: c["nome"] for c in painel["contas"]}
            verificar(
                sem_nome.get("aluno.b@unoesc.edu.br") == "",
                "quem ainda não abriu o perfil aparece sem nome, e não com lixo",
            )
            client.get("/api/profile", headers=auth(token_b3))
            depois = client.get("/api/admin/panorama", headers=auth(token_a2)).json()
            nomes = {c["username"]: c["nome"] for c in depois["contas"]}
            verificar(
                nomes.get("aluno.b@unoesc.edu.br") == "Aluno B",
                "o nome do Moodle chega ao painel depois da primeira visita",
            )

            # A matrícula do secret veio sem domínio e o login tem domínio: se
            # a comparação fosse literal, o dono ficaria de fora do próprio
            # painel dependendo de como digitou o login.
            verificar(
                painel["resumo"]["total"] >= 2 and "servidor" in painel,
                "o painel traz resumo e estado do servidor",
            )

            # O aluno comum não pode nem descobrir que a rota existe.
            verificar(
                client.get("/api/admin/panorama", headers=auth(token_b3)).status_code == 404,
                "aluno comum recebe 404 no painel, não 403",
            )
            verificar(
                client.get("/api/me", headers=auth(token_b3)).json()["is_admin"] is False,
                "aluno comum não é anunciado como admin",
            )
            verificar(
                client.get("/api/admin/panorama").status_code == 401,
                "sem sessão nenhuma o painel exige login antes de tudo",
            )

            # O painel olha todo mundo; o que ele NÃO pode fazer é levar junto
            # o que abre a conta de alguém.
            bruto = resposta.text.lower()
            vazamentos = [
                termo for termo in
                ("password", "senha", "token", "ics_token", "endpoint", "p256dh", "auth\"")
                if termo in bruto
            ]
            verificar(
                not vazamentos,
                f"o painel não devolve credencial de aluno (achado: {vazamentos})",
            )
        finally:
            os.environ.pop("ADMIN_USERNAMES", None)

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
