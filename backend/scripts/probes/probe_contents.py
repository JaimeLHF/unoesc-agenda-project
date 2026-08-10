#!/usr/bin/env python3
"""
Descobre o que existe DENTRO das disciplinas — atividades, prazos, e se
há datas que não chegaram ao calendário.

Uso:  python3 probe_contents.py

Só stdlib.
"""
import getpass
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

BASE = "https://on.unoesc.edu.br"
TIMEOUT = 40
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
TZ_BR = timezone(timedelta(hours=-3))

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [("User-Agent", UA)]


def get(url):
    with opener.open(url, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    with opener.open(urllib.request.Request(url, data=body), timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace"), r.geturl()


def ajax(sesskey, methodname, args):
    url = f"{BASE}/lib/ajax/service.php?sesskey={urllib.parse.quote(sesskey)}&info={methodname}"
    payload = json.dumps([{"index": 0, "methodname": methodname, "args": args}]).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=TIMEOUT) as r:
        out = json.loads(r.read().decode("utf-8", "replace"))
    item = out[0] if isinstance(out, list) and out else {}
    if item.get("error"):
        exc = item.get("exception", {})
        raise RuntimeError(f"{exc.get('errorcode')}: {exc.get('message')}")
    return item.get("data")


def fmt(ts):
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return "-"
    return datetime.fromtimestamp(ts, TZ_BR).strftime("%d/%m/%Y %H:%M") if ts > 0 else "-"


def login():
    user = input("Usuário do Moodle: ").strip()
    pwd = getpass.getpass("Senha: ")
    page = get(f"{BASE}/login/index.php")
    m = re.search(r'name="logintoken"\s+value="([^"]+)"', page)
    html, _ = post_form(f"{BASE}/login/index.php", {
        "username": user, "password": pwd,
        "logintoken": m.group(1) if m else "", "anchor": "",
    })
    if re.search(r'name="logintoken"', html):
        print("✗ login recusado")
        sys.exit(1)
    sk = re.search(r'"sesskey":"([^"]+)"', html)
    if not sk:
        sk = re.search(r'"sesskey":"([^"]+)"', get(f"{BASE}/my/"))
    print("✓ logado\n")
    return sk.group(1)


def modname_de(m):
    """
    Slug do módulo (assign, quiz, hsuforum...).

    Cuidado: no `core_courseformat_get_state` o campo `module` vem com o nome
    de exibição TRADUZIDO ("Tarefa", "Questionário") — filtrar por slug nele
    nunca casa. A URL é a fonte confiável e independente de idioma.
    """
    m_url = re.search(r"/mod/([a-z0-9_]+)/", m.get("url") or "")
    if m_url:
        return m_url.group(1)
    return m.get("modname") or m.get("plugin") or m.get("module") or "?"


def conteudo_via_html(cid):
    """Fallback: lê a página do curso e conta os módulos de atividade."""
    html = get(f"{BASE}/course/view.php?id={cid}")
    mods = re.findall(r'/mod/([a-z0-9_]+)/view\.php\?id=(\d+)', html)
    nomes = re.findall(r'(?is)<span class="instancename">(.*?)</span>', html)
    return mods, [re.sub(r"<[^>]+>", "", n).strip()[:60] for n in nomes]


def main():
    sesskey = login()

    d = ajax(sesskey, "core_course_get_enrolled_courses_by_timeline_classification",
             {"offset": 0, "limit": 0, "classification": "all", "sort": "fullname",
              "customfieldname": "", "customfieldvalue": ""})
    courses = (d or {}).get("courses", [])
    print(f"{len(courses)} disciplinas\n" + "=" * 70)

    total_ativ = entregaveis = so_html = 0
    ENTREGAVEIS = {"assign", "quiz", "workshop", "lesson"}

    for c in courses:
        cid, nome = c.get("id"), c.get("fullname", "")
        print(f"\n[{cid}] {nome}")

        # -- tentativa 1: API de conteúdo do curso -------------------------
        secs = None
        for fn in ("core_course_get_contents",
                   "core_courseformat_get_state"):
            try:
                secs = ajax(sesskey, fn, {"courseid": cid})
                print(f"    (via {fn})")
                break
            except Exception as exc:
                print(f"    · {fn}: {exc}")

        # core_courseformat_get_state devolve o estado como STRING JSON, não
        # como objeto — sem esse parse a resposta boa era descartada e o script
        # caía no fallback de HTML sem necessidade.
        if isinstance(secs, str):
            try:
                secs = json.loads(secs)
                print("      (resposta era string JSON — parseada)")
            except json.JSONDecodeError:
                pass

        mods = []
        if isinstance(secs, list):
            mods = [m for s in secs if isinstance(s, dict) for m in s.get("modules", [])]
        elif isinstance(secs, dict):
            print(f"      (chaves: {sorted(secs.keys())})")
            mods = secs.get("cm") or []

        if mods:
            total_ativ += len(mods)
            print(f"    {len(mods)} atividades")
            tipos = {}
            for m in mods:
                t = modname_de(m)
                tipos[t] = tipos.get(t, 0) + 1
            print("    tipos:", ", ".join(f"{v}x {k}" for k, v in sorted(tipos.items(), key=lambda x: -x[1])))
            entregaveis += sum(v for k, v in tipos.items() if k in ENTREGAVEIS)
            # atividades com data
            for m in mods:
                dates = m.get("dates") or []
                if dates:
                    rot = "; ".join(f"{dd.get('label', '').strip()} {fmt(dd.get('timestamp'))}"
                                    for dd in dates)
                    print(f"      • {(m.get('name') or '')[:50]:52} [{m.get('modname')}] {rot}")
        else:
            # -- fallback: HTML da página do curso -------------------------
            try:
                pares, nomes = conteudo_via_html(cid)
                tipos = {}
                for t, _ in pares:
                    tipos[t] = tipos.get(t, 0) + 1
                print(f"    (via HTML) {len(pares)} links de atividade")
                if tipos:
                    print("    tipos:", ", ".join(f"{v}x {k}" for k, v in sorted(tipos.items(), key=lambda x: -x[1])))
                entregaveis += sum(v for k, v in tipos.items() if k in ENTREGAVEIS)
                for n in nomes[:12]:
                    print(f"      • {n}")
                total_ativ += len(pares)
                so_html += 1
            except Exception as exc:
                print(f"    ✗ HTML também falhou: {exc}")

    print("\n" + "=" * 70)
    print(f"TOTAL: {total_ativ} atividades em {len(courses)} disciplinas")
    print(f"       {entregaveis} entregáveis (assign/quiz) — é o que vira agenda")

    if so_html:
        # O fallback de HTML não lê data nenhuma; qualquer contagem de datas
        # aqui seria zero por construção. Não confunda isso com "sem prazo".
        print(f"\n⚠ {so_html}/{len(courses)} disciplinas caíram no fallback de HTML"
              " (core_course_get_contents desabilitado neste Moodle).")
        print("  Datas por atividade NÃO foram verificadas nessas — use o calendário")
        print("  (probe_calendar.py) como fonte de prazo, não este script.")

    if total_ativ == 0:
        print("→ Cursos vazios no Moodle. Nenhuma fonte automática de agenda existe.")
    elif entregaveis == 0:
        print("→ Só material e fórum, zero entregáveis: a agenda automática não tem"
              " o que mostrar para este aluno (típico de curso presencial).")
    else:
        print("→ Há datas nas atividades. Dá pra montar agenda mesmo sem o calendário.")


if __name__ == "__main__":
    main()
