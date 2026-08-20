#!/usr/bin/env python3
"""
Painel de administração — roda na máquina do dono, nunca no servidor.

Por que não é um endpoint: qualquer rota que devolva a lista de alunos quebra a
regra de que toda busca é por `(user_id, ...)`, e colocaria no ar, atrás de uma
senha só, o inventário inteiro de quem usa o app. O painel resolve o mesmo
problema sem abrir nada: baixa uma cópia do banco pelo `fly ssh` (o mesmo
caminho do `backup-db.sh`), lê localmente e escreve um HTML na pasta `.admin/`,
que está no `.gitignore`. O que sai daqui tem matrícula de aluno dentro — é
arquivo local, não se publica.

    make admin              # baixa o banco de produção e abre o painel
    make admin ARGS=--local # usa a cópia já baixada, sem tocar no Fly

Só biblioteca padrão: o painel precisa rodar mesmo com a venv do backend
quebrada, que é justamente quando se quer olhar para ele.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = "unoesc-agenda"
DOMINIO = f"https://{APP}.fly.dev"
RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / ".admin"
BANCO = PASTA / "agenda.db"
SAIDA = PASTA / "painel.html"

# O Fly não é obrigado a responder rápido, e o painel não pode ficar pendurado:
# sem log ele ainda mostra o banco, que é a parte que importa.
TIMEOUT_FLY = 90


# ---------------------------------------------------------------------------
# Coleta
# ---------------------------------------------------------------------------

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def fly(*args: str, timeout: int = TIMEOUT_FLY) -> str:
    """Roda o flyctl e devolve a saída limpa; string vazia se falhar."""
    caminho = shutil.which("fly") or shutil.which("flyctl")
    if not caminho:
        return ""
    try:
        r = subprocess.run(
            [caminho, *args, "-a", APP],
            capture_output=True, text=True, timeout=timeout,
        )
        return ANSI.sub("", r.stdout if r.returncode == 0 else r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return ""


def acordar() -> None:
    """
    A máquina pode estar suspensa, e o `sftp get` não a acorda — quem acorda é
    uma requisição HTTP comum pelo proxy. Mesmo motivo do `backup-db.sh`.
    """
    for _ in range(10):
        try:
            urllib.request.urlopen(f"{DOMINIO}/api/health/live", timeout=20).read()
            return
        except Exception:
            time.sleep(3)


def baixar_banco() -> None:
    """
    Baixa para um arquivo ao lado e só então substitui. A primeira versão
    escrevia direto no destino e só reclamava se o arquivo não existisse — como
    a cópia anterior continuava lá, um download falho passava batido e o painel
    mostrava o banco de ontem com o carimbo de hoje. Silêncio é o único
    resultado inaceitável aqui.
    """
    PASTA.mkdir(exist_ok=True)
    print("acordando o servidor…")
    acordar()
    print("baixando /data/agenda.db…")
    temp = BANCO.with_suffix(".novo")
    temp.unlink(missing_ok=True)
    saida = fly("ssh", "sftp", "get", "/data/agenda.db", str(temp))

    # O flyctl às vezes sai com 0 sem escrever nada (agente wireguard
    # reiniciando, máquina suspensa). O cabeçalho é a prova de que veio banco.
    ok = temp.exists() and temp.stat().st_size > 0
    if ok:
        with temp.open("rb") as f:
            ok = f.read(16).startswith(b"SQLite format 3")
    if not ok:
        temp.unlink(missing_ok=True)
        print(saida.strip() or "o flyctl não trouxe o banco", file=sys.stderr)
        print(
            "download falhou — o painel NÃO foi gerado, para não mostrar dado "
            "velho como se fosse de agora. Tente de novo, ou use --local de "
            "propósito.",
            file=sys.stderr,
        )
        sys.exit(1)
    temp.replace(BANCO)


def saude() -> dict:
    try:
        with urllib.request.urlopen(f"{DOMINIO}/api/health", timeout=30) as r:
            return json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "erro", "checks": {}, "hints": [f"sem resposta: {exc}"]}


LINHA_LOG = re.compile(
    r"(?P<data>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<nivel>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"\[agenda\]\s+(?P<msg>.*)"
)
REQUISICAO = re.compile(r"(?P<metodo>[A-Z]+) (?P<rota>/\S*) → (?P<status>\d{3}) em (?P<ms>[\d.]+)ms")


def ler_logs() -> dict:
    """
    Resume o buffer de log do Fly: volume de requisições, rotas mais chamadas,
    tempo, e as linhas de erro na íntegra — que é o que se procura quando algo
    quebrou.
    """
    bruto = fly("logs", "--no-tail")
    linhas = bruto.splitlines()
    rotas: Counter[str] = Counter()
    status: Counter[str] = Counter()
    duracoes: list[float] = []
    erros: list[str] = []
    lentas: list[tuple[float, str]] = []

    for linha in linhas:
        m = LINHA_LOG.search(linha)
        if not m:
            continue
        if m["nivel"] in ("ERROR", "CRITICAL", "WARNING"):
            erros.append(f'{m["data"]}  {m["nivel"]}  {m["msg"]}')
        req = REQUISICAO.search(m["msg"])
        if req:
            rotas[f'{req["metodo"]} {req["rota"]}'] += 1
            status[req["status"]] += 1
            ms = float(req["ms"])
            duracoes.append(ms)
            lentas.append((ms, f'{req["metodo"]} {req["rota"]}'))

    duracoes.sort()
    lentas.sort(reverse=True)
    return {
        "linhas": len(linhas),
        "requisicoes": len(duracoes),
        "rotas": rotas.most_common(8),
        "status": sorted(status.items()),
        "mediana": duracoes[len(duracoes) // 2] if duracoes else None,
        "p95": duracoes[int(len(duracoes) * 0.95)] if duracoes else None,
        "lentas": lentas[:5],
        "erros": erros[-12:],
        "vazio": not bruto.strip(),
    }


def ler_banco() -> dict:
    con = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    q = lambda sql, *p: con.execute(sql, p).fetchall()
    um = lambda sql, *p: con.execute(sql, p).fetchone()[0]

    # O nome só existe em banco baixado depois de 20/08/2026; uma cópia mais
    # antiga ainda abre, sem a coluna.
    tem_nome = any(
        c[1] == "full_name" for c in con.execute("pragma table_info(users)")
    )
    campo_nome = "u.full_name" if tem_nome else "'' as full_name"

    alunos = q(
        f"""
        select u.moodle_username, {campo_nome}, u.created_at, u.last_login_at, u.plan,
               u.ai_calls_used, u.ics_token is not null as tem_ics,
               (select count(*) from subjects s where s.user_id = u.id) as disciplinas,
               (select count(*) from events e where e.user_id = u.id) as eventos,
               (select count(*) from done_events d where d.user_id = u.id) as concluidos,
               (select count(*) from push_subscriptions p where p.user_id = u.id) as aparelhos,
               (select count(*) from sessions x where x.user_id = u.id) as sessoes
          from users u
         order by u.last_login_at desc
        """
    )
    return {
        "alunos": [dict(a) for a in alunos],
        "total": um("select count(*) from users"),
        "ativos_24h": um("select count(*) from users where last_login_at > datetime('now','-1 day')"),
        "ativos_7d": um("select count(*) from users where last_login_at > datetime('now','-7 day')"),
        "sessoes": um("select count(*) from sessions"),
        "sessoes_vivas": um("select count(*) from sessions where last_used_at > datetime('now','-8 hour')"),
        "aparelhos": um("select count(*) from push_subscriptions"),
        "push_alunos": um("select count(distinct user_id) from push_subscriptions"),
        "push_falhando": um("select count(*) from push_subscriptions where falhas > 0"),
        "eventos": um("select count(*) from events"),
        "eventos_pdf": um("select count(*) from events where source = 'pdf_curso'"),
        "disciplinas": um("select count(*) from subjects"),
        "itens": um("select count(*) from course_items"),
        "por_dia": [(r[0], r[1]) for r in q(
            "select date(created_at), count(*) from users group by 1 order by 1"
        )],
        "ultimo_scrape": [dict(r) for r in q(
            """
            select u.moodle_username, m.value
              from meta m join users u on u.id = m.user_id
             where m.key like '%scrape%' order by m.value desc
            """
        )],
        "tamanho": BANCO.stat().st_size,
    }


# ---------------------------------------------------------------------------
# Apresentação
# ---------------------------------------------------------------------------

def quando(iso: str | None) -> str:
    """'há 3h' — o número absoluto não responde 'isso é recente?'."""
    if not iso:
        return "—"
    try:
        t = datetime.fromisoformat(iso.replace("Z", "")).replace(tzinfo=timezone.utc)
    except ValueError:
        return iso
    d = datetime.now(timezone.utc) - t
    if d < timedelta(minutes=2):
        return "agora"
    if d < timedelta(hours=1):
        return f"há {int(d.total_seconds() // 60)}min"
    if d < timedelta(days=1):
        return f"há {int(d.total_seconds() // 3600)}h"
    if d < timedelta(days=30):
        return f"há {d.days}d"
    return t.strftime("%d/%m/%Y")


def e(v) -> str:
    return html.escape(str(v))


def cartao(rotulo: str, valor, nota: str = "") -> str:
    return (
        f'<div class="cartao"><div class="valor">{e(valor)}</div>'
        f'<div class="rotulo">{e(rotulo)}</div>'
        f'{f"<div class=nota>{e(nota)}</div>" if nota else ""}</div>'
    )


def render(dados: dict, health: dict, logs: dict, status_fly: str) -> str:
    agora = datetime.fromtimestamp(BANCO.stat().st_mtime).strftime("%d/%m/%Y às %H:%M")

    linhas = "".join(
        "<tr>"
        f"<td><div>{e(a['full_name'] or 'sem nome ainda')}</div>"
        f"<div class=mono style='opacity:.65'>{e(a['moodle_username'])}</div></td>"
        f"<td>{e(quando(a['last_login_at']))}</td>"
        f"<td>{e(quando(a['created_at']))}</td>"
        f"<td class=num>{e(a['disciplinas'])}</td>"
        f"<td class=num>{e(a['eventos'])}</td>"
        f"<td class=num>{e(a['concluidos'])}</td>"
        f"<td>{'🔔 ' + str(a['aparelhos']) if a['aparelhos'] else '—'}</td>"
        f"<td>{'sim' if a['tem_ics'] else '—'}</td>"
        f"<td class=num>{e(a['ai_calls_used'])}</td>"
        "</tr>"
        for a in dados["alunos"]
    )

    checks = "".join(
        f'<li class="{"ok" if v else "ruim"}">{e(k)}</li>'
        for k, v in (health.get("checks") or {}).items()
    ) or (
        '<li class=discreto>modo --local: o servidor não foi consultado</li>'
        if health.get("status") == "pulado"
        else "<li class=ruim>sem resposta do servidor</li>"
    )

    novos = "".join(
        f'<li><span class=mono>{e(d)}</span> — {e(n)} conta(s)</li>'
        for d, n in dados["por_dia"]
    )

    rotas = "".join(
        f"<tr><td class=mono>{e(r)}</td><td class=num>{e(n)}</td></tr>"
        for r, n in logs["rotas"]
    ) or "<tr><td colspan=2>sem requisição no buffer</td></tr>"

    erros = "".join(f"<div class=erro>{e(x)}</div>" for x in logs["erros"]) or \
        "<p class=discreto>Nenhum WARNING ou ERROR no buffer de log.</p>"

    lentas = "".join(
        f"<li>{e(rota)} — <b>{ms:.0f}ms</b></li>" for ms, rota in logs["lentas"]
    ) or "<li class=discreto>—</li>"

    tempos = (
        f'mediana {logs["mediana"]:.0f}ms · p95 {logs["p95"]:.0f}ms'
        if logs["mediana"] is not None else "sem amostra"
    )

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Painel — Agenda UNOESC</title>
<style>
  :root {{
    --fundo:#f6f7f9; --caixa:#fff; --texto:#16181d; --fraco:#6b7280;
    --borda:#e3e6ea; --ok:#137a4b; --ruim:#b3261e; --marca:#1b4dd8;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --fundo:#0f1115; --caixa:#171a21; --texto:#e8eaee; --fraco:#9aa3b2;
      --borda:#252932; --ok:#48c78e; --ruim:#ff6b60; --marca:#7aa2ff;
    }}
  }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; padding:28px 20px 64px; background:var(--fundo); color:var(--texto);
    font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }}
  main {{ max-width:1040px; margin:0 auto }}
  h1 {{ font-size:22px; margin:0 0 2px }}
  h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.06em;
    color:var(--fraco); margin:34px 0 12px }}
  .discreto {{ color:var(--fraco) }}
  .cartoes {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)) }}
  .cartao {{ background:var(--caixa); border:1px solid var(--borda); border-radius:12px; padding:14px 16px }}
  .valor {{ font-size:28px; font-weight:650; line-height:1.1 }}
  .rotulo {{ color:var(--fraco); font-size:13px; margin-top:2px }}
  .nota {{ color:var(--fraco); font-size:12px; margin-top:6px }}
  .painel {{ background:var(--caixa); border:1px solid var(--borda); border-radius:12px; padding:16px }}
  table {{ width:100%; border-collapse:collapse; font-size:14px }}
  th {{ text-align:left; color:var(--fraco); font-weight:600; font-size:12px;
    text-transform:uppercase; letter-spacing:.04em; padding:0 10px 8px }}
  td {{ padding:9px 10px; border-top:1px solid var(--borda) }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums }}
  .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px }}
  ul.checks {{ list-style:none; padding:0; margin:0; display:flex; flex-wrap:wrap; gap:8px }}
  ul.checks li {{ padding:4px 10px; border-radius:999px; font-size:13px;
    border:1px solid var(--borda) }}
  ul.checks .ok {{ color:var(--ok) }}
  ul.checks .ruim {{ color:var(--ruim) }}
  .erro {{ font-family:ui-monospace,monospace; font-size:12.5px; color:var(--ruim);
    padding:6px 0; border-bottom:1px solid var(--borda); white-space:pre-wrap }}
  pre {{ overflow-x:auto; font-size:12.5px; margin:0; color:var(--fraco) }}
  .duas {{ display:grid; gap:16px; grid-template-columns:1fr 1fr }}
  @media (max-width:720px) {{ .duas {{ grid-template-columns:1fr }} }}
  .rodape {{ margin-top:40px; color:var(--fraco); font-size:13px;
    border-top:1px solid var(--borda); padding-top:14px }}
  code {{ background:var(--fundo); padding:1px 6px; border-radius:5px }}
</style></head><body><main>

<h1>Agenda UNOESC — painel do dono</h1>
<p class="discreto">Banco de produção copiado em {e(agora)} · {dados['tamanho'] / 1024:.0f} KB
· arquivo local, não publique</p>

<h2>Quem está usando</h2>
<div class="cartoes">
  {cartao("contas criadas", dados["total"])}
  {cartao("ativos em 24h", dados["ativos_24h"])}
  {cartao("ativos em 7 dias", dados["ativos_7d"])}
  {cartao("sessões abertas", dados["sessoes_vivas"], f"{dados['sessoes']} no banco")}
  {cartao("aparelhos com aviso", dados["aparelhos"], f"{dados['push_alunos']} aluno(s)" + (f" · {dados['push_falhando']} falhando" if dados["push_falhando"] else ""))}
</div>

<h2>Contas</h2>
<div class="painel"><table>
<tr><th>aluno</th><th>último acesso</th><th>entrou</th><th class=num>disc.</th>
<th class=num>eventos</th><th class=num>feitos</th><th>push</th><th>.ics</th><th class=num>Lumi</th></tr>
{linhas}
</table></div>

<h2>Dados guardados</h2>
<div class="cartoes">
  {cartao("disciplinas", dados["disciplinas"])}
  {cartao("eventos", dados["eventos"], f"{dados['eventos_pdf']} vindos de PDF")}
  {cartao("itens de sala", dados["itens"])}
</div>

<h2>Servidor</h2>
<div class="duas">
  <div class="painel">
    <p class="discreto" style="margin-top:0">Diagnóstico de <code>/api/health</code></p>
    <ul class="checks">{checks}</ul>
    <p class="discreto">Requisições no buffer de log: <b>{e(logs["requisicoes"])}</b> · {e(tempos)}</p>
    <p class="discreto" style="margin-bottom:4px">Mais lentas:</p>
    <ul class="discreto" style="margin:0;padding-left:18px">{lentas}</ul>
  </div>
  <div class="painel">
    <p class="discreto" style="margin-top:0">Rotas mais chamadas</p>
    <table>{rotas}</table>
  </div>
</div>

<h2>Erros recentes</h2>
<div class="painel">{erros}</div>

<h2>Contas novas por dia</h2>
<div class="painel"><ul style="margin:0;padding-left:18px">{novos}</ul></div>

<h2>Máquina no Fly</h2>
<div class="painel"><pre>{e(status_fly.strip() or "sem resposta do flyctl")}</pre></div>

<p class="rodape">
Gerado por <code>make admin</code>. O buffer de log do Fly guarda poucas horas —
para investigar algo antigo, <code>fly logs -a {APP}</code> no momento em que acontece.
Este arquivo tem matrícula de aluno: ele fica em <code>.admin/</code>, que o git ignora.
</p>
</main></body></html>"""


# ---------------------------------------------------------------------------

def main() -> None:
    local = "--local" in sys.argv
    if local and not BANCO.exists():
        print("não há cópia local ainda — rode sem --local", file=sys.stderr)
        sys.exit(1)
    if not local:
        baixar_banco()

    print("lendo o banco…")
    dados = ler_banco()
    health = {"status": "pulado", "checks": {}, "hints": []} if local else saude()
    logs = ler_logs() if not local else {
        "linhas": 0, "requisicoes": 0, "rotas": [], "status": [],
        "mediana": None, "p95": None, "lentas": [], "erros": [], "vazio": True,
    }
    status_fly = "modo --local — o Fly não foi consultado." if local else fly("status")

    PASTA.mkdir(exist_ok=True)
    SAIDA.write_text(render(dados, health, logs, status_fly), encoding="utf-8")
    print(f"✅ {SAIDA}")

    for abridor in ("wslview", "xdg-open", "open"):
        if shutil.which(abridor):
            subprocess.Popen(
                [abridor, str(SAIDA)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            break


if __name__ == "__main__":
    main()
