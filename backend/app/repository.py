"""
Repositório — encapsula leituras/escritas no banco.

Não tem lógica de negócio: só CRUD + upsert. Os endpoints do FastAPI
chamam as funções daqui.

**Regra do multi-tenant**: toda função que toca cache do aluno recebe
`user_id` e filtra por ele. Não existe query global neste módulo — se um dia
aparecer uma, ela vaza a agenda de um aluno para outro.
"""

import secrets
from datetime import timedelta
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.moodle import normalizar_login
from app.database import (
    AppSession,
    CourseItem,
    DoneEvent,
    PushSubscription,
    Event,
    Meta,
    SessionLocal,
    Subject,
    User,
    event_key,
    new_id,
    utc_now,
)


# Por quantos dias a tela continua avisando que um prazo mudou de data. Não é
# até o evento chegar: um trabalho adiado em março ainda apareceria como
# "adiado" na véspera da entrega, e o aviso perderia o sentido de novidade.
DIAS_AVISO_MUDANCA = 14

# Por quantos dias um item recém-publicado na sala conta como novidade. Uma
# semana é o intervalo com que o aluno abre a agenda; passou disso, ou ele já
# viu, ou o aviso virou paisagem.
DIAS_MATERIAL_NOVO = 7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_session() -> Session:
    """Sessão única para um request. Quem chama é responsável pelo close()."""
    return SessionLocal()


def _aviso_valido(quando, dias: int = DIAS_AVISO_MUDANCA) -> bool:
    """O aviso ainda está dentro da janela em que vale a pena mostrar?"""
    if quando is None:
        return False
    # O SQLite devolve datetime ingênuo; comparar com um aware levanta
    # TypeError. Normaliza para o mesmo formato de `utc_now()`.
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=utc_now().tzinfo)
    return (utc_now() - quando) <= timedelta(days=dias)


def aviso_de_mudanca(event: Event) -> Optional[str]:
    """
    A data anterior deste evento, se a troca for recente. Nulo faz a tela não
    desenhar o selo — é assim que o aviso expira sem job de limpeza.
    """
    if not event.previous_date or event.previous_date == event.date:
        return None
    return event.previous_date if _aviso_valido(event.date_changed_at) else None


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------

def set_full_name(session: Session, user_id: str, nome: str) -> None:
    """
    Guarda o nome que o Moodle devolveu, se veio algum.

    Escreve só quando muda: esta função é chamada a cada visita ao perfil, e
    gravar o mesmo texto de novo seria uma escrita por visita sem nenhuma
    informação nova. Nome vazio não apaga o que já está lá — o Moodle já
    respondeu sem cadastro em falha temporária, e apagar seria silencioso.
    """
    limpo = (nome or "").strip()
    if not limpo:
        return
    user = session.get(User, user_id)
    if user is not None and user.full_name != limpo:
        user.full_name = limpo


def get_or_create_user(session: Session, moodle_username: str) -> User:
    """
    Devolve o usuário do login informado, criando na primeira vez.

    Não há cadastro no app: quem valida a senha é o Moodle, e só chegamos aqui
    depois de um login bem-sucedido.
    """
    # `294833` e `294833@unoesc.edu.br` são a mesma pessoa — ver
    # `normalizar_login`. A conta é criada por esta função, então é aqui que a
    # regra precisa valer, e não só no endpoint de login.
    normalized = normalizar_login(moodle_username)
    user = session.execute(
        select(User).where(User.moodle_username == normalized)
    ).scalar_one_or_none()

    if user is None:
        user = User(id=new_id(), moodle_username=normalized)
        session.add(user)
        session.flush()
    else:
        user.last_login_at = utc_now()

    return user


def get_user(session: Session, user_id: str) -> Optional[User]:
    return session.get(User, user_id)


def delete_user(session: Session, user_id: str) -> None:
    """
    Apaga a conta e tudo que pertence a ela: cache, concluídos, metadados e
    sessões abertas. Suporte ao "excluir minha conta" exigido pela LGPD.
    """
    session.execute(delete(Event).where(Event.user_id == user_id))
    session.execute(delete(Subject).where(Subject.user_id == user_id))
    session.execute(delete(DoneEvent).where(DoneEvent.user_id == user_id))
    session.execute(delete(CourseItem).where(CourseItem.user_id == user_id))
    session.execute(delete(PushSubscription).where(PushSubscription.user_id == user_id))
    session.execute(delete(Meta).where(Meta.user_id == user_id))
    session.execute(delete(AppSession).where(AppSession.user_id == user_id))
    session.execute(delete(User).where(User.id == user_id))


def get_or_create_ics_token(session: Session, user_id: str) -> Optional[str]:
    """Chave do calendário assinável do aluno, criada na primeira vez."""
    user = session.get(User, user_id)
    if user is None:
        return None
    if not user.ics_token:
        user.ics_token = secrets.token_urlsafe(24)
        session.flush()
    return user.ics_token


def reset_ics_token(session: Session, user_id: str) -> Optional[str]:
    """Troca a chave: o endereço antigo para de funcionar na hora."""
    user = session.get(User, user_id)
    if user is None:
        return None
    user.ics_token = secrets.token_urlsafe(24)
    session.flush()
    return user.ics_token


def get_user_by_ics_token(session: Session, token: str) -> Optional[User]:
    """
    Dono de uma chave de calendário.

    É a única leitura do módulo que não recebe `user_id` — ela existe
    justamente para descobrir de quem é a agenda, a partir de um segredo que
    só o dono tem. Quem chama usa o `id` devolvido para filtrar tudo o mais.
    """
    if not token:
        return None
    return session.execute(
        select(User).where(User.ics_token == token)
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Notificação push
# ---------------------------------------------------------------------------

def salvar_inscricao(
    session: Session,
    user_id: str,
    endpoint: str,
    p256dh: str,
    auth: str,
    password_enc: Optional[str],
) -> None:
    """
    Registra (ou atualiza) a inscrição de um aparelho.

    A PK é o `endpoint` porque é ele que o navegador troca quando reinstala o
    app — o mesmo aluno no mesmo celular pode gerar endpoint novo, e aí é uma
    inscrição nova mesmo.
    """
    stmt = sqlite_insert(PushSubscription).values(
        endpoint=endpoint,
        user_id=user_id,
        p256dh=p256dh,
        auth=auth,
        password_enc=password_enc,
        created_at=utc_now(),
        falhas=0,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[PushSubscription.endpoint],
        set_={
            # Um endpoint que reaparece pertence a quem acabou de autorizar.
            # Sem isto, um celular emprestado continuaria mandando os avisos de
            # um aluno para a conta do outro.
            "user_id": stmt.excluded.user_id,
            "p256dh": stmt.excluded.p256dh,
            "auth": stmt.excluded.auth,
            "password_enc": stmt.excluded.password_enc,
            "falhas": 0,
        },
    )
    session.execute(stmt)


def remover_inscricao(session: Session, user_id: str, endpoint: str) -> None:
    """Desliga um aparelho. A senha guardada vai junto — é o combinado."""
    session.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint
        )
    )


def remover_inscricoes(session: Session, user_id: str) -> None:
    """Desliga todos os aparelhos do aluno."""
    session.execute(delete(PushSubscription).where(PushSubscription.user_id == user_id))


def listar_inscricoes(session: Session, user_id: str) -> list[PushSubscription]:
    return list(
        session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user_id)
        ).scalars()
    )


def usuarios_com_push(session: Session) -> list[str]:
    """
    Os `user_id` que têm ao menos um aparelho inscrito.

    **A única consulta global do módulo**, e ela existe porque o disparo das
    notificações não nasce de um request de aluno nenhum: nasce do relógio. Ela
    devolve só identificadores — quem lê agenda continua sendo as funções por
    `user_id`, uma conta de cada vez. Ver `scheduler.py`.
    """
    return [
        linha[0]
        for linha in session.execute(select(PushSubscription.user_id).distinct())
    ]


def registrar_falha_push(session: Session, endpoint: str, morta: bool = False) -> None:
    """
    Uma entrega falhou. `morta` descarta na hora (404/410 do serviço de push);
    o resto conta até o teto e some — falha isolada é rede, falha sempre é
    aparelho que não existe mais.
    """
    from app import push

    if morta:
        session.execute(
            delete(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        return

    inscricao = session.get(PushSubscription, endpoint)
    if inscricao is None:
        return
    inscricao.falhas += 1
    if inscricao.falhas >= push.MAX_FALHAS:
        session.delete(inscricao)


def marcar_envio(session: Session, endpoint: str) -> None:
    inscricao = session.get(PushSubscription, endpoint)
    if inscricao is not None:
        inscricao.falhas = 0
        inscricao.last_sent_at = utc_now()


# ---------------------------------------------------------------------------
# Subjects + Events (cache do scraping)
# ---------------------------------------------------------------------------

def upsert_subjects(session: Session, user_id: str, subjects: list[dict]) -> None:
    """
    Insere ou atualiza cada disciplina. A PK é (user_id, name).

    Quando a nota final muda — inclusive de "nenhuma" para a primeira —, a nota
    velha vai para `previous_grade` e a hora fica em `grade_changed_at`. É o
    aviso de "saiu nota", o motivo pelo qual o aluno abre o Moodle no celular
    várias vezes por semana.

    Disciplina que aparece pela primeira vez nunca vira aviso: quem se cadastra
    no meio do semestre não quer receber as notas antigas como novidade. Mesma
    regra do `baseline` dos materiais.
    """
    anteriores = {
        row.name: row
        for row in session.execute(
            select(
                Subject.name, Subject.final_grade, Subject.previous_grade,
                Subject.grade_changed_at,
            ).where(Subject.user_id == user_id)
        )
    }

    for s in subjects:
        nota = s.get("final_grade")
        antes = anteriores.get(s["name"])

        if antes is None:
            # Primeiro encontro com esta disciplina: registra sem anunciar.
            previous_grade, grade_changed_at = None, None
        elif nota is not None and nota != antes.final_grade:
            previous_grade, grade_changed_at = antes.final_grade, utc_now()
        else:
            # Nota igual (ou o Moodle não respondeu): mantém o aviso que já
            # estava lá, que ainda pode não ter sido visto.
            previous_grade, grade_changed_at = antes.previous_grade, antes.grade_changed_at

        s["grade_changed"] = _aviso_valido(grade_changed_at)
        s["previous_grade"] = previous_grade if s["grade_changed"] else None

        stmt = sqlite_insert(Subject).values(
            user_id=user_id,
            name=s["name"],
            content=s.get("content"),
            dof=s.get("dof"),
            course_id=str(s["course_id"]) if s.get("course_id") else None,
            course_url=s.get("course_url"),
            start_date=s.get("start_date"),
            end_date=s.get("end_date"),
            final_grade=nota,
            previous_grade=previous_grade,
            grade_changed_at=grade_changed_at,
            updated_at=utc_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Subject.user_id, Subject.name],
            set_={
                "content": stmt.excluded.content,
                "dof": stmt.excluded.dof,
                "course_id": stmt.excluded.course_id,
                "course_url": stmt.excluded.course_url,
                "start_date": stmt.excluded.start_date,
                "end_date": stmt.excluded.end_date,
                # O Moodle às vezes não responde o relatório de notas; nesse
                # caso `nota` vem nula e sobrescrever apagaria a nota guardada.
                "final_grade": (
                    stmt.excluded.final_grade if nota is not None else Subject.final_grade
                ),
                "previous_grade": stmt.excluded.previous_grade,
                "grade_changed_at": stmt.excluded.grade_changed_at,
                "updated_at": utc_now(),
            },
        )
        session.execute(stmt)


def aviso_de_nota(subject: Subject) -> tuple[bool, Optional[float]]:
    """
    (saiu nota?, nota anterior) — o par que a tela usa para desenhar o selo.

    A nota anterior é nula quando esta é a primeira da disciplina, que é o caso
    mais comum: "Nota lançada" em vez de "8,0 → 8,5".
    """
    if not _aviso_valido(subject.grade_changed_at):
        return False, None
    return True, subject.previous_grade


def upsert_events(session: Session, user_id: str, events: list[dict]) -> None:
    """
    Insere ou atualiza cada evento usando (user_id, stable_key) como identidade.
    Eventos antigos (que não vieram no scrape mais recente) NÃO são removidos
    — preserva histórico.

    Quando a data de um evento que já existia muda, a data velha é guardada em
    `previous_date`: é o que permite a tela dizer "adiado" em vez de trocar o
    dia sem avisar. O aviso é reaproveitado nos scrapes seguintes (a data não
    muda toda hora) e expira sozinho por `date_changed_at` — ver
    `DIAS_AVISO_MUDANCA`.
    """
    # Uma consulta para todos: o laço faria uma por evento, e um semestre
    # inteiro passa de cem.
    anteriores = {
        row.stable_key: row
        for row in session.execute(
            select(
                Event.stable_key, Event.date, Event.previous_date, Event.date_changed_at
            ).where(Event.user_id == user_id)
        )
    }

    for e in events:
        key = event_key(e)
        e["stable_key"] = key  # devolvido ao frontend, que não recalcula mais

        antes = anteriores.get(key)
        if antes is not None and antes.date != e["date"]:
            previous_date, date_changed_at = antes.date, utc_now()
        elif antes is not None:
            # Mesma data: preserva o aviso que já estava lá em vez de apagá-lo
            # no scrape seguinte, que é quando o aluno costuma vê-lo.
            previous_date, date_changed_at = antes.previous_date, antes.date_changed_at
        else:
            previous_date, date_changed_at = None, None

        e["previous_date"] = previous_date if _aviso_valido(date_changed_at) else None

        stmt = sqlite_insert(Event).values(
            user_id=user_id,
            stable_key=key,
            title=e["title"],
            date=e["date"],
            time=e.get("time"),
            description=e.get("description"),
            subject=e["subject"],
            type=e["type"],
            source=e.get("source"),
            url=e.get("url"),
            previous_date=previous_date,
            date_changed_at=date_changed_at,
            weight=e.get("weight"),
            last_seen_at=utc_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Event.user_id, Event.stable_key],
            set_={
                "title": stmt.excluded.title,
                "date": stmt.excluded.date,
                "time": stmt.excluded.time,
                "description": stmt.excluded.description,
                "type": stmt.excluded.type,
                "source": stmt.excluded.source,
                "url": stmt.excluded.url,
                "previous_date": stmt.excluded.previous_date,
                "date_changed_at": stmt.excluded.date_changed_at,
                "weight": stmt.excluded.weight,
                "last_seen_at": utc_now(),
            },
        )
        session.execute(stmt)


# ---------------------------------------------------------------------------
# Material publicado na sala (o "apareceu coisa nova")
# ---------------------------------------------------------------------------

def registrar_materiais(
    session: Session, user_id: str, subject: str, itens: list[dict]
) -> None:
    """
    Registra o que a sala da disciplina tem hoje, marcando o que é novo.

    Na primeira vez que uma disciplina passa por aqui, tudo entra como
    `baseline`: quem se cadastra no meio do semestre não quer receber os 58
    arquivos de trás como novidade. A partir daí, cmid que não estava na tabela
    é item que o professor publicou depois.

    Item removido da sala não é apagado daqui — o registro é do que o aluno já
    viu, e apagar faria o item ressurgir como novidade se o professor
    republicasse.
    """
    if not itens:
        return

    ja_vistos = {
        row.cmid
        for row in session.execute(
            select(CourseItem.cmid).where(
                CourseItem.user_id == user_id, CourseItem.subject == subject
            )
        )
    }
    primeira_vez = not ja_vistos
    agora = utc_now()

    for item in itens:
        cmid = str(item.get("cmid") or "").strip()
        if not cmid or cmid in ja_vistos:
            continue
        ja_vistos.add(cmid)  # o mesmo cmid repetido na lista violaria a PK
        session.add(CourseItem(
            user_id=user_id,
            cmid=cmid,
            subject=subject,
            name=item.get("name") or "(sem nome)",
            modname=item.get("modname"),
            url=item.get("url"),
            first_seen_at=agora,
            baseline=1 if primeira_vez else 0,
        ))


def novidades_por_disciplina(
    session: Session, user_id: str, dias: int = DIAS_MATERIAL_NOVO
) -> dict[str, list[dict]]:
    """O que apareceu em cada sala nos últimos `dias`, ignorando o baseline."""
    corte = utc_now() - timedelta(days=dias)
    # Comparação com datetime ingênuo, que é o que o SQLite guarda.
    corte = corte.replace(tzinfo=None)

    linhas = session.execute(
        select(CourseItem)
        .where(
            CourseItem.user_id == user_id,
            CourseItem.baseline == 0,
            CourseItem.first_seen_at >= corte,
        )
        .order_by(CourseItem.first_seen_at.desc())
    ).scalars().all()

    novidades: dict[str, list[dict]] = {}
    for item in linhas:
        novidades.setdefault(item.subject, []).append({
            "name": item.name,
            "url": item.url,
            "modname": item.modname,
            "first_seen_at": item.first_seen_at.isoformat() if item.first_seen_at else None,
        })
    return novidades


def set_google_event_id(
    session: Session, user_id: str, stable_key: str, google_event_id: str
) -> None:
    """
    Registra o ID do evento criado no Google Calendar. É o que permite ao
    frontend mostrar o evento como já sincronizado depois de um reload.
    """
    session.execute(
        update(Event)
        .where(Event.user_id == user_id, Event.stable_key == stable_key)
        .values(google_event_id=google_event_id)
    )


def list_synced_keys(session: Session, user_id: str) -> list[str]:
    """`stable_key` de todo evento do aluno que já foi para o Google Calendar."""
    rows = session.execute(
        select(Event.stable_key).where(
            Event.user_id == user_id, Event.google_event_id.is_not(None)
        )
    ).all()
    return [r[0] for r in rows]


def list_subjects(session: Session, user_id: str) -> list[Subject]:
    return list(
        session.execute(
            select(Subject).where(Subject.user_id == user_id).order_by(Subject.name)
        ).scalars()
    )


def get_subject(session: Session, user_id: str, name: str) -> Optional[Subject]:
    return session.get(Subject, (user_id, name))


def get_event(session: Session, user_id: str, stable_key: str) -> Optional[Event]:
    """
    Um evento do aluno pela chave estável.

    A busca é sempre por (user_id, stable_key) — a chave primária composta. É
    o que faz um link de atividade compartilhado abrir só para quem tem aquela
    atividade na própria agenda.
    """
    return session.get(Event, (user_id, stable_key))


def list_events(session: Session, user_id: str) -> list[Event]:
    return list(
        session.execute(
            select(Event)
            .where(Event.user_id == user_id)
            .order_by(Event.date.asc(), Event.time.asc().nulls_first())
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Done events
# ---------------------------------------------------------------------------

def list_done_keys(session: Session, user_id: str) -> list[str]:
    rows = session.execute(
        select(DoneEvent.stable_key).where(DoneEvent.user_id == user_id)
    ).all()
    return [r[0] for r in rows]


def mark_done(session: Session, user_id: str, stable_key: str) -> None:
    """Idempotente — marcar duas vezes não dá erro."""
    stmt = sqlite_insert(DoneEvent).values(
        user_id=user_id, stable_key=stable_key, completed_at=utc_now()
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[DoneEvent.user_id, DoneEvent.stable_key]
    )
    session.execute(stmt)


def unmark_done(session: Session, user_id: str, stable_key: str) -> None:
    session.execute(
        delete(DoneEvent).where(
            DoneEvent.user_id == user_id, DoneEvent.stable_key == stable_key
        )
    )


# ---------------------------------------------------------------------------
# Meta (timestamps livres)
# ---------------------------------------------------------------------------

def set_meta(session: Session, user_id: str, key: str, value: str) -> None:
    stmt = sqlite_insert(Meta).values(user_id=user_id, key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Meta.user_id, Meta.key], set_={"value": stmt.excluded.value}
    )
    session.execute(stmt)


def get_meta(session: Session, user_id: str, key: str) -> Optional[str]:
    row = session.execute(
        select(Meta.value).where(Meta.user_id == user_id, Meta.key == key)
    ).first()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Operações de manutenção
# ---------------------------------------------------------------------------

def clear_cache(session: Session, user_id: str) -> None:
    """
    Apaga subjects, events e meta **do aluno informado**. Mantém
    intencionalmente os done_events — o usuário não quer perder o que já marcou
    como concluído ao limpar cache.
    """
    session.execute(delete(Event).where(Event.user_id == user_id))
    session.execute(delete(Subject).where(Subject.user_id == user_id))
    session.execute(delete(CourseItem).where(CourseItem.user_id == user_id))
    session.execute(delete(Meta).where(Meta.user_id == user_id))
