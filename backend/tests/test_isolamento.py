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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app import ratelimit  # noqa: E402

# Credenciais aceitas pelo Moodle falso, e a agenda que cada uma devolve.
CONTAS = {
    "aluno.a@unoesc.edu.br": "senha-a",
    "aluno.b@unoesc.edu.br": "senha-b",
}

AGENDAS = {
    "aluno.a@unoesc.edu.br": {
        "subjects": [{
            "id": "1", "name": "Cálculo I", "content": "",
            "dof": "CAL1", "course_id": 101, "course_url": "https://on.unoesc.edu.br/course/view.php?id=101",
        }],
        "calendar_events": [{
            "moodle_event_id": 9001, "title": "Prova 1", "date": "2099-05-10",
            "time": "19:00", "description": "", "subject": "Cálculo I",
            "type": "exam", "source": "moodle_calendar", "url": None,
        }],
    },
    "aluno.b@unoesc.edu.br": {
        "subjects": [{
            "id": "2", "name": "Redes de Computadores", "content": "",
            "dof": "RED1", "course_id": 202, "course_url": "https://on.unoesc.edu.br/course/view.php?id=202",
        }],
        "calendar_events": [{
            "moodle_event_id": 9002, "title": "Trabalho de Redes", "date": "2099-06-20",
            "time": None, "description": "", "subject": "Redes de Computadores",
            "type": "deadline", "source": "moodle_calendar", "url": None,
        }],
    },
}


class MoodleFalso:
    """Dublê do `MoodleClient`: valida credencial e devolve agenda fixa."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, username, password):
        if CONTAS.get(username) != password:
            raise PermissionError("Usuário ou senha inválidos.")

    def run(self, username, password):
        self.login(username, password)
        # Cópia profunda rasa: `upsert_events` escreve `stable_key` no dict.
        agenda = AGENDAS[username]
        return {
            "subjects": [dict(s) for s in agenda["subjects"]],
            "calendar_events": [dict(e) for e in agenda["calendar_events"]],
        }


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


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main_teste() -> int:
    with TestClient(main.app) as client:
        print("\n[1] Dois alunos, duas agendas")
        token_a = entrar(client, "aluno.a@unoesc.edu.br")
        token_b = entrar(client, "aluno.b@unoesc.edu.br")
        verificar(token_a != token_b, "tokens diferentes para alunos diferentes")

        client.post("/api/scrape", headers=auth(token_a))
        client.post("/api/scrape", headers=auth(token_b))

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
        ]
        for metodo, rota, corpo in sem_sessao:
            resp = getattr(client, metodo)(rota, json=corpo) if corpo else getattr(client, metodo)(rota)
            verificar(resp.status_code == 401, f"{metodo.upper()} {rota} → 401 sem token")

        print("\n[4] Token de A não alcança dados de B")
        # `open-course` sem `target_url` resolve pelo cache do dono do token.
        resp = client.post(
            "/api/open-course",
            json={"subject_name": "Redes de Computadores"},
            headers=auth(token_a),
        )
        verificar(resp.status_code == 404, "A não consegue abrir disciplina de B")

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
