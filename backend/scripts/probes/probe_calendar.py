#!/usr/bin/env python3
"""
Compara as funções de calendário do Moodle pra descobrir qual devolve
a agenda COMPLETA (não só o que tem ação pendente).

Uso:  python3 probe_calendar.py [meses]     # padrão: 4 meses à frente

Só stdlib.
"""
import getpass
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

BASE = "https://on.unoesc.edu.br"
TIMEOUT = 30
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
    if not ts:
        return "sem data"
    return datetime.fromtimestamp(ts, TZ_BR).strftime("%d/%m/%Y %H:%M")


def show(events, limit=12):
    """Imprime eventos usando os TIMESTAMPS, não o formattedtime (que é HTML)."""
    for e in events[:limit]:
        course = (e.get("course") or {}).get("shortname") or ""
        print(f"        {fmt(e.get('timestart')):17} | {(e.get('eventtype') or '?'):12}"
              f" | {(e.get('modulename') or '-'):8} | {(e.get('name') or '')[:52]}")
        if course:
            print(f"                          ↳ {course[:70]}")


def login():
    user = input("Usuário do Moodle: ").strip()
    pwd = getpass.getpass("Senha: ")
    page = get(f"{BASE}/login/index.php")
    m = re.search(r'name="logintoken"\s+value="([^"]+)"', page)
    html, final = post_form(f"{BASE}/login/index.php", {
        "username": user, "password": pwd,
        "logintoken": m.group(1) if m else "", "anchor": "",
    })
    if re.search(r'name="logintoken"', html):
        print("✗ login recusado")
        sys.exit(1)
    sk = re.search(r'"sesskey":"([^"]+)"', html)
    if not sk:
        html = get(f"{BASE}/my/")
        sk = re.search(r'"sesskey":"([^"]+)"', html)
    print(f"✓ logado (sesskey ok)\n")
    return sk.group(1)


def main():
    meses = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    sesskey = login()
    agora = int(time.time())
    resultados = {}

    # ---- A. action events (o que usamos hoje) ----------------------------
    print("[A] core_calendar_get_action_events_by_timesort  (só AÇÃO PENDENTE)")
    try:
        d = ajax(sesskey, "core_calendar_get_action_events_by_timesort",
                 {"limitnum": 50, "timesortfrom": agora - 86400 * 60,
                  "limittononsuspendedevents": True})
        ev = (d or {}).get("events", [])
        resultados["action_events"] = len(ev)
        print(f"    → {len(ev)} eventos")
        show(ev)
    except Exception as exc:
        print(f"    ✗ {exc}")

    # ---- B. upcoming view -----------------------------------------------
    print("\n[B] core_calendar_get_calendar_upcoming_view")
    try:
        d = ajax(sesskey, "core_calendar_get_calendar_upcoming_view",
                 {"courseid": 1, "categoryid": 0})
        ev = (d or {}).get("events", [])
        resultados["upcoming_view"] = len(ev)
        print(f"    → {len(ev)} eventos")
        show(ev)
    except Exception as exc:
        print(f"    ✗ {exc}")

    # ---- C. monthly view, N meses ---------------------------------------
    print(f"\n[C] core_calendar_get_calendar_monthly_view  ({meses} meses)")
    hoje = datetime.now(TZ_BR)
    todos, vistos = [], set()
    for i in range(meses):
        ano = hoje.year + (hoje.month - 1 + i) // 12
        mes = (hoje.month - 1 + i) % 12 + 1
        try:
            d = ajax(sesskey, "core_calendar_get_calendar_monthly_view",
                     {"year": ano, "month": mes, "courseid": 1,
                      "categoryid": 0, "includenavigation": False, "mini": False})
            mes_ev = [e for w in (d or {}).get("weeks", [])
                      for day in w.get("days", [])
                      for e in day.get("events", [])]
            novos = [e for e in mes_ev if e.get("id") not in vistos]
            for e in novos:
                vistos.add(e.get("id"))
            todos.extend(novos)
            print(f"    {mes:02d}/{ano}: {len(mes_ev):3} eventos ({len(novos)} novos)")
        except Exception as exc:
            print(f"    {mes:02d}/{ano}: ✗ {exc}")
    resultados["monthly_view"] = len(todos)
    todos.sort(key=lambda e: e.get("timestart") or 0)
    print(f"    → {len(todos)} eventos únicos no total")
    show(todos, limit=20)

    # ---- D. tipos de evento encontrados ---------------------------------
    if todos:
        print("\n[D] tipos de evento (eventtype / modulename)")
        tipos = {}
        for e in todos:
            k = f"{e.get('eventtype')} / {e.get('modulename') or '-'}"
            tipos[k] = tipos.get(k, 0) + 1
        for k, v in sorted(tipos.items(), key=lambda x: -x[1]):
            print(f"        {v:3}x  {k}")

        print("\n[E] campos disponíveis num evento (pra modelar o schema)")
        amostra = todos[0]
        for k in sorted(amostra.keys()):
            v = amostra[k]
            v = json.dumps(v, ensure_ascii=False)[:70] if isinstance(v, (dict, list)) else str(v)[:70]
            print(f"        {k:24} = {v}")

    # ---- F. export .ics --------------------------------------------------
    print("\n[F] /calendar/export.php — estrutura do form")
    try:
        exp = get(f"{BASE}/calendar/export.php")
        forms = re.findall(r'(?is)<form[^>]*action="([^"]*)"[^>]*>', exp)
        inputs = re.findall(r'(?is)<input[^>]*name="([^"]+)"[^>]*?(?:value="([^"]*)")?[^>]*>', exp)
        print(f"    forms: {forms}")
        print(f"    campos: {sorted(set(n for n, _ in inputs))}")
        tok = re.search(r"authtoken=([A-Za-z0-9]+)", exp)
        if tok:
            print(f"    ✓ authtoken já na página: …{tok.group(1)[-6:]}")
    except Exception as exc:
        print(f"    ✗ {exc}")

    print("\n=== PLACAR ===")
    for k, v in resultados.items():
        print(f"    {k:16} {v} eventos")
    print("\nA função com mais eventos é a que deve alimentar a agenda.")


if __name__ == "__main__":
    main()
