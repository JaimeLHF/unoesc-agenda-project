"""
Painel do dono — a única parte do app que olha para todos os alunos de uma vez.

Isso contraria a regra que sustenta o resto do backend ("toda busca é por
`(user_id, ...)`"), e por isso o acesso é fechado de três formas:

1. **Não existe sem configuração.** Sem o secret `ADMIN_USERNAMES` no
   ambiente, os endpoints respondem 404 — não 401. Numa instalação que não
   quer painel, a rota simplesmente não está lá.
2. **Não tem senha própria.** Quem entra é uma matrícula da lista, com a mesma
   sessão do app. Senha nova seria mais um segredo para vazar, e um segredo
   que não expira.
3. **Não devolve o que é do aluno.** Nada de senha cifrada, token de sessão,
   chave do .ics ou endpoint de push — nem o conteúdo das disciplinas. O
   painel responde "quem entrou, quanto usou e o servidor está bem?", que é a
   pergunta de quem mantém o serviço no ar. Para as outras, existe o aluno.

O que sai daqui ainda é dado pessoal: matrícula é gente identificável. A tela
diz isso, e o app continua não sendo serviço oficial da UNOESC.
"""

from __future__ import annotations

import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import observability


def _lista() -> set[str]:
    """Matrículas com acesso ao painel, do secret `ADMIN_USERNAMES`."""
    bruto = os.getenv("ADMIN_USERNAMES", "")
    return {p.strip().lower() for p in bruto.split(",") if p.strip()}


def configurado() -> bool:
    return bool(_lista())


def e_admin(username: str) -> bool:
    """
    Aceita a matrícula com ou sem `@unoesc.edu.br`: o mesmo aluno entra das
    duas formas no Moodle, e cadastrar só uma delas trancaria o dono para fora
    dependendo de como ele digitou o login.
    """
    if not username:
        return False
    atual = username.strip().lower()
    curto = atual.split("@")[0]
    permitidos = _lista()
    if not permitidos:
        return False
    return atual in permitidos or any(p.split("@")[0] == curto for p in permitidos)


def panorama(db: Session) -> dict:
    """Tudo que o painel mostra, numa consulta por seção."""

    def um(sql: str) -> int:
        return db.execute(text(sql)).scalar_one()

    contas = [
        {
            "username": r.moodle_username,
            "criado_em": str(r.created_at),
            "ultimo_acesso": str(r.last_login_at),
            "plano": r.plan,
            "disciplinas": r.disciplinas,
            "eventos": r.eventos,
            "concluidos": r.concluidos,
            "aparelhos": r.aparelhos,
            "sessoes": r.sessoes,
            "assinou_ics": bool(r.tem_ics),
            "lumi": r.ai_calls_used,
        }
        for r in db.execute(text("""
            select u.moodle_username, u.created_at, u.last_login_at, u.plan,
                   u.ai_calls_used, u.ics_token is not null as tem_ics,
                   (select count(*) from subjects s where s.user_id = u.id) as disciplinas,
                   (select count(*) from events e where e.user_id = u.id) as eventos,
                   (select count(*) from done_events d where d.user_id = u.id) as concluidos,
                   (select count(*) from push_subscriptions p where p.user_id = u.id) as aparelhos,
                   (select count(*) from sessions x where x.user_id = u.id
                     and x.last_used_at > datetime('now','-8 hour')) as sessoes
              from users u
             order by u.last_login_at desc
        """))
    ]

    return {
        "contas": contas,
        "resumo": {
            "total": um("select count(*) from users"),
            "novos_hoje": um(
                "select count(*) from users where date(created_at) = date('now')"
            ),
            "ativos_24h": um(
                "select count(*) from users where last_login_at > datetime('now','-1 day')"
            ),
            "ativos_7d": um(
                "select count(*) from users where last_login_at > datetime('now','-7 day')"
            ),
            "sessoes_vivas": um(
                "select count(*) from sessions where last_used_at > datetime('now','-8 hour')"
            ),
            "aparelhos": um("select count(*) from push_subscriptions"),
            "push_alunos": um("select count(distinct user_id) from push_subscriptions"),
            "push_falhando": um("select count(*) from push_subscriptions where falhas > 0"),
            "disciplinas": um("select count(*) from subjects"),
            "eventos": um("select count(*) from events"),
            "eventos_pdf": um("select count(*) from events where source = 'pdf_curso'"),
            "itens_sala": um("select count(*) from course_items"),
        },
        "por_dia": [
            {"dia": r[0], "contas": r[1]}
            for r in db.execute(text("""
                select date(created_at), count(*) from users
                 group by 1 order by 1 desc limit 30
            """))
        ],
        "servidor": observability.metricas(),
    }
