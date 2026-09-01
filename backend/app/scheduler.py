"""
O relógio que dispara as notificações.

## Os quatro horários

    07:00  resumo do dia + o que mudou desde ontem
    13:00  só o que mudou (nota lançada, prazo alterado) — e, quando não
           mudou nada e o aluno sumiu há dias, um empurrãozinho
    17:00  o que começa daqui a pouco — **não fala com o Moodle**
    19:00  véspera ("amanhã tem prova") + o que mudou

Três idas ao Moodle, e não uma por hora: cada rodada faz um login **por aluno
inscrito**, mais uma requisição de boletim por disciplina (ver `_boletins`), e
o Moodle da UNOESC não é nosso para bombardear. Três também é o teto de barulho
que a rotina do aluno aguenta sem ele desligar tudo — e notificação desligada
no Android não se recupera.

O lembrete das 17h é o quarto horário e não quebra essa conta: ele lê só o
banco (`SLOTS_SEM_MOODLE`), custa zero requisição, e só existe quando há
compromisso com hora marcada nas próximas horas. O resumo das 7h fala do dia
inteiro e some da tela até a webconferência das 19h chegar.

## Por que o servidor precisa da senha aqui

"Saiu nota" só existe se o servidor consultar o Moodle com o app fechado. A
senha da sessão morre por inatividade — e nem enquanto viva ela serve, porque
o aluno não está com o app aberto às 7h da manhã. Quem opta por notificação guarda a senha cifrada junto da inscrição —
está escrito na tela de opt-in, e some no instante em que ele desliga. Ver
`database.PushSubscription`.

## Como ele sobrevive a reinício e a máquina suspensa

O último disparo de cada horário fica no banco, não em memória: no Fly a
máquina suspende quando ninguém acessa, e um deploy reinicia o processo. Sem
essa marca, voltar do sono no meio da janela mandaria o resumo de novo.

Se a máquina estiver suspensa **na hora exata**, o disparo não acontece — o
processo não está rodando para olhar o relógio. É por isso que o `fly.toml`
mantém uma máquina de pé, e por que existe o `/api/push/run` para um cron
externo acordar o app.
"""

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from app import crypto, push
from app import repository as repo
from app.database import event_key
from app.moodle import TZ_BR, MoodleClient

logger = logging.getLogger("agenda.scheduler")

# Hora (no fuso de Brasília) → nome do disparo.
HORARIOS = {7: "manha", 13: "meio", 17: "lembrete", 19: "noite"}

# Disparos que não abrem o Moodle: falam só do que já está no banco.
SLOTS_SEM_MOODLE = {"lembrete"}

# Janela do lembrete da tarde. Meia hora de piso porque aviso que chega junto
# com o começo não serve para nada; cinco horas de teto para que o disparo das
# 17h alcance a webconferência das 19h e não a entrega das 23:59, que o resumo
# do dia já anunciou de manhã.
LEMBRETE_MIN = timedelta(minutes=30)
LEMBRETE_MAX = timedelta(hours=5)

# O empurrãozinho de quem sumiu (`push.LEMBRETES_DE_HABITO`). Só sai para quem
# não abre o app há `DIAS_SEM_ABRIR` dias — quem entrou ontem já sabe que o app
# existe, e mandar "lembre-se de atualizar" para ele é o aviso que ensina a
# ignorar os outros. `DIAS_ENTRE_HABITOS` é o piso entre dois: um a cada três
# dias é lembrete; um por dia é o que faz o aluno desligar tudo.
DIAS_SEM_ABRIR = 3
DIAS_ENTRE_HABITOS = 3

# De quanto em quanto tempo o laço acorda para olhar o relógio. Um minuto é
# folgado: a janela de tolerância abaixo é bem maior que isso.
INTERVALO_S = 60

# Quanto tempo depois da hora ainda vale disparar. Cobre a máquina que estava
# suspensa às 7h em ponto e acordou às 7h20 com a primeira visita do dia — o
# resumo atrasado ainda serve; à tarde já não.
TOLERANCIA = timedelta(hours=2)

# Dono das marcas de "já disparei hoje". Não é um aluno: é a linha do sistema
# na tabela `meta`, que é chaveada por (user_id, key). Um id que não sai do
# `uuid4` do `new_id()` nunca colide com usuário de verdade.
DONO_SISTEMA = "__sistema__"


def _agora() -> datetime:
    return datetime.now(TZ_BR)


def _ja_disparou(slot: str, dia: date) -> bool:
    with repo.get_session() as db:
        marca = repo.get_meta(db, DONO_SISTEMA, f"push:{slot}")
    return marca == dia.isoformat()


def _marcar_disparo(slot: str, dia: date) -> None:
    with repo.get_session() as db:
        repo.set_meta(db, DONO_SISTEMA, f"push:{slot}", dia.isoformat())
        db.commit()


def slot_pendente(agora: Optional[datetime] = None) -> Optional[str]:
    """
    Qual disparo está na hora e ainda não aconteceu hoje. `None` se não há.

    Função pura o suficiente para ser chamada de teste: recebe o instante.
    """
    agora = agora or _agora()
    for hora, slot in HORARIOS.items():
        marcado = agora.replace(hour=hora, minute=0, second=0, microsecond=0)
        if marcado <= agora <= marcado + TOLERANCIA and not _ja_disparou(slot, agora.date()):
            return slot
    return None


# ---------------------------------------------------------------------------
# O que mudou desde a última visita
# ---------------------------------------------------------------------------

def _estado_atual(user_id: str) -> tuple[dict[str, Optional[float]], dict[str, str]]:
    """Notas e datas que o banco tem agora, antes de falar com o Moodle."""
    with repo.get_session() as db:
        notas = {s.name: s.final_grade for s in repo.list_subjects(db, user_id)}
        datas = {e.stable_key: e.date for e in repo.list_events(db, user_id)}
    return notas, datas


def _diferencas(
    resultado: dict,
    notas_antes: dict[str, Optional[float]],
    datas_antes: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """
    (disciplinas com nota nova, eventos que mudaram de data).

    Comparado aqui, contra o retrato tirado antes do scrape, e não pelo
    `grade_changed` do banco: aquele campo fica ligado por duas semanas de
    propósito, para a tela poder mostrar o selo — usá-lo aqui mandaria a mesma
    notificação todo dia durante duas semanas.
    """
    notas_novas = [
        s for s in resultado["subjects"]
        if s.get("final_grade") is not None
        # Disciplina que aparece agora não vira aviso: quem acabou de se
        # inscrever não quer o semestre inteiro de notas antigas.
        and s["name"] in notas_antes
        and s["final_grade"] != notas_antes[s["name"]]
    ]

    prazos = []
    for e in resultado["calendar_events"]:
        chave = event_key(e)
        anterior = datas_antes.get(chave)
        if anterior and anterior != e["date"]:
            prazos.append({**e, "previous_date": anterior})

    return notas_novas, prazos


def _boletins(moodle: MoodleClient, subjects: list[dict]) -> dict[str, list[dict]]:
    """
    Boletim item a item de cada disciplina, na mesma sessão já logada do `run()`.

    É o custo desta função: uma requisição por disciplina em cada disparo — no
    caso real, 7 disciplinas × 3 horários. O `run()` não faz isso porque ele
    também roda quando o aluno abre a agenda, e ali cada requisição extra é
    espera na tela; aqui ninguém está olhando.

    `course_grade_items` já engole a própria falha e devolve `[]`, e
    `registrar_notas_itens` trata lista vazia como "não veio", nunca como
    "as notas sumiram".
    """
    boletins: dict[str, list[dict]] = {}
    for sub in subjects:
        try:
            course_id = int(sub.get("course_id") or 0)
        except (TypeError, ValueError):
            continue
        if course_id:
            boletins[sub["name"]] = moodle.course_grade_items(course_id)
    return boletins


def _do_dia(user_id: str, dia: str) -> list[dict]:
    """Eventos de uma data que o aluno ainda não marcou como concluídos."""
    with repo.get_session() as db:
        feitos = set(repo.list_done_keys(db, user_id))
        return [
            {
                "title": e.title, "date": e.date, "time": e.time,
                "subject": e.subject, "type": e.type,
            }
            for e in repo.list_events(db, user_id)
            if e.date == dia and e.stable_key not in feitos
        ]


def _em_breve(user_id: str, agora: datetime) -> tuple[list[dict], int]:
    """
    (compromissos de hoje que começam dentro da janela, minutos até o primeiro).

    Só entra evento com hora marcada: "23:59" de uma entrega é convenção do
    Moodle para "fim do dia", não hora de começar nada.
    """
    proximos: list[tuple[timedelta, dict]] = []
    for e in _do_dia(user_id, agora.date().isoformat()):
        hora = e.get("time") or ""
        try:
            h, m = hora.split(":")[:2]
            quando = agora.replace(
                hour=int(h), minute=int(m), second=0, microsecond=0
            )
        except (ValueError, TypeError):
            continue
        falta = quando - agora
        if LEMBRETE_MIN <= falta <= LEMBRETE_MAX:
            proximos.append((falta, e))

    if not proximos:
        return [], 0

    proximos.sort(key=lambda par: par[0])
    return [e for _, e in proximos], int(proximos[0][0].total_seconds() // 60)


def _dias_desde(marca: Optional[str], agora: datetime) -> int:
    """
    Quantos dias desde a marca guardada no `meta`. Sem marca, um número grande.

    Aceita data (`2026-09-01`) e instante (`2026-09-01T13:00:00+00:00`): a
    primeira é do envio deste aviso, a segunda é do `last_scraped_at`.
    """
    if not marca:
        return 10_000
    try:
        quando = datetime.fromisoformat(marca)
    except ValueError:
        return 10_000
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=agora.tzinfo)
    return (agora - quando).days


def _habito(user_id: str, agora: datetime) -> Optional[tuple[tuple[str, str, str], int]]:
    """
    (aviso de hábito, próximo índice) para quem sumiu — ou `None`.

    Duas perguntas antes de falar: faz dias que ele não abre o app? E faz dias
    que este aviso não sai? Só o "sim" nas duas justifica uma notificação sem
    fato novo por trás.
    """
    with repo.get_session() as db:
        aberto_em = repo.get_meta(db, user_id, "last_scraped_at")
        enviado_em = repo.get_meta(db, user_id, "push:habito")
        indice = repo.get_meta(db, user_id, "push:habito:frase")

    if _dias_desde(aberto_em, agora) < DIAS_SEM_ABRIR:
        return None
    if _dias_desde(enviado_em, agora) < DIAS_ENTRE_HABITOS:
        return None

    try:
        atual = int(indice or 0)
    except ValueError:
        atual = 0
    return push.habito(atual), atual + 1


def _marcar_habito(user_id: str, agora: datetime, proximo: int) -> None:
    """Guarda quando saiu e qual frase vem depois — a rotação é por aluno."""
    with repo.get_session() as db:
        repo.set_meta(db, user_id, "push:habito", agora.date().isoformat())
        repo.set_meta(db, user_id, "push:habito:frase", str(proximo))
        db.commit()


# ---------------------------------------------------------------------------
# Disparo
# ---------------------------------------------------------------------------

def entregar(user_id: str, aviso: Optional[tuple[str, str, str]], tag: str) -> int:
    """Manda um aviso para todos os aparelhos do aluno. Devolve quantos foram."""
    if aviso is None:
        return 0

    titulo, corpo, url = aviso
    enviados = 0

    with repo.get_session() as db:
        inscricoes = repo.listar_inscricoes(db, user_id)

    for inscricao in inscricoes:
        endpoint = inscricao.endpoint
        try:
            push.enviar(push.para_dict(inscricao), titulo, corpo, url, tag=tag)
        except push.InscricaoMorta:
            logger.info("inscrição morta descartada (%s…)", endpoint[:40])
            with repo.get_session() as db:
                repo.registrar_falha_push(db, endpoint, morta=True)
                db.commit()
            continue
        except Exception as exc:
            logger.warning("push falhou (%s…): %s", endpoint[:40], exc)
            with repo.get_session() as db:
                repo.registrar_falha_push(db, endpoint)
                db.commit()
            continue

        enviados += 1
        with repo.get_session() as db:
            repo.marcar_envio(db, endpoint)
            db.commit()

    return enviados


def _credencial(user_id: str) -> Optional[tuple[str, str]]:
    """(usuário, senha) guardados na inscrição, ou `None` se não dá para logar."""
    with repo.get_session() as db:
        usuario = repo.get_user(db, user_id)
        inscricoes = repo.listar_inscricoes(db, user_id)

    if usuario is None:
        return None

    for inscricao in inscricoes:
        if not inscricao.password_enc:
            continue
        senha = crypto.decrypt(inscricao.password_enc)
        if senha:
            return usuario.moodle_username, senha
    return None


def atender(user_id: str, slot: str) -> int:
    """
    Uma conta, um disparo. Devolve quantas notificações saíram.

    Nunca levanta: um aluno com senha trocada não pode impedir o aviso dos
    outros.
    """
    enviados = 0
    try:
        # O lembrete da tarde não abre o Moodle: o que ele anuncia já está no
        # banco desde o disparo da manhã, e um quarto login por aluno seria
        # pagar requisição para reler o mesmo dado.
        credencial = None if slot in SLOTS_SEM_MOODLE else _credencial(user_id)

        # Sem credencial guardada ainda dá para avisar do que já está no banco.
        # O resumo do dia sai do cache; só "saiu nota" precisa do Moodle.
        if credencial is not None:
            notas_antes, datas_antes = _estado_atual(user_id)
            with MoodleClient() as moodle:
                resultado = moodle.run(*credencial)
                boletins = _boletins(moodle, resultado["subjects"])

            with repo.get_session() as db:
                repo.upsert_subjects(db, user_id, resultado["subjects"])
                if resultado["calendar_events"]:
                    repo.upsert_events(db, user_id, resultado["calendar_events"])
                for sub in resultado["subjects"]:
                    repo.registrar_materiais(
                        db, user_id, sub["name"], sub.get("activities") or []
                    )
                notas_item = [
                    nova
                    for nome, itens in boletins.items()
                    for nova in repo.registrar_notas_itens(db, user_id, nome, itens)
                ]
                db.commit()

            notas_novas, prazos = _diferencas(resultado, notas_antes, datas_antes)
            # Um fato, uma notificação. O boletim item a item ganha do total da
            # disciplina porque diz *qual* avaliação saiu — e porque o total
            # fica `None` durante boa parte do semestre, enquanto o Moodle não
            # dá peso a todas as avaliações. Foi esse silêncio que fez a nota
            # 9,0 de Desenvolvimento Mobile chegar por e-mail da UNOESC e não
            # pelo app. O total só é usado quando o relatório do item não veio.
            enviados += entregar(
                user_id,
                push.notas_de_item(notas_item) or push.notas_novas(notas_novas),
                "nota",
            )
            enviados += entregar(user_id, push.prazos_alterados(prazos), "prazo")

        hoje = _agora().date()
        if slot == "manha":
            enviados += entregar(
                user_id, push.resumo_do_dia(_do_dia(user_id, hoje.isoformat())), "dia"
            )
        elif slot == "meio" and enviados == 0:
            # Só quando o disparo não teve nada de concreto a dizer: nota
            # lançada e prazo alterado são o motivo pelo qual ele ligou os
            # avisos, e um empurrãozinho na mesma leva rouba a atenção deles.
            agora = _agora()
            proposta = _habito(user_id, agora)
            if proposta is not None:
                aviso, proximo = proposta
                saiu = entregar(user_id, aviso, "habito")
                if saiu:
                    _marcar_habito(user_id, agora, proximo)
                enviados += saiu
        elif slot == "lembrete":
            agora = _agora()
            proximos, minutos = _em_breve(user_id, agora)
            enviados += entregar(user_id, push.lembrete(proximos, minutos), "lembrete")
        elif slot == "noite":
            amanha = (hoje + timedelta(days=1)).isoformat()
            enviados += entregar(user_id, push.vespera(_do_dia(user_id, amanha)), "vespera")

    except Exception as exc:  # um aluno não derruba a rodada dos outros
        logger.warning("notificação falhou para %s: %s", user_id, exc)

    return enviados


def rodar(slot: str) -> dict:
    """Executa um disparo inteiro. Chamado pelo laço e pelo `/api/push/run`."""
    if not push.configurado():
        logger.info("VAPID ausente — nada a disparar")
        return {"slot": slot, "usuarios": 0, "notificacoes": 0}

    with repo.get_session() as db:
        usuarios = repo.usuarios_com_push(db)

    total = sum(atender(uid, slot) for uid in usuarios)
    _marcar_disparo(slot, _agora().date())

    logger.info("disparo %s: %d aluno(s), %d notificação(ões)", slot, len(usuarios), total)
    return {"slot": slot, "usuarios": len(usuarios), "notificacoes": total}


async def laco() -> None:
    """
    Acorda de minuto em minuto e dispara o que estiver na hora.

    Roda dentro do processo do app em vez de um worker separado: são três
    execuções por dia sobre poucos alunos, e um segundo processo significaria
    outra máquina no Fly e outro caminho para o mesmo SQLite — que só aceita um
    dono.
    """
    if not push.configurado():
        logger.info("VAPID ausente — laço de notificações não sobe")
        return

    logger.info("laço de notificações no ar (horários: %s)", sorted(HORARIOS))
    while True:
        try:
            slot = slot_pendente()
            if slot:
                # `to_thread` porque o disparo fala com o Moodle por HTTP
                # síncrono; no laço de eventos ele travaria a API inteira.
                await asyncio.to_thread(rodar, slot)
        except Exception as exc:  # o laço não pode morrer
            logger.exception("erro no laço de notificações: %s", exc)
        await asyncio.sleep(INTERVALO_S)


def token_do_cron() -> str:
    """
    Segredo que autoriza o `/api/push/run`. Vazio desliga o endpoint.

    Existe para quem quiser deixar a máquina do Fly dormindo e acordá-la de
    fora (cron-job.org, GitHub Actions). Sem isso, o endereço seria um botão
    público de "mande notificação para todo mundo agora".
    """
    return os.getenv("PUSH_CRON_TOKEN", "").strip()
