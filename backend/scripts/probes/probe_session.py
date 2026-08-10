#!/usr/bin/env python3
"""
Testa login HTTP direto no Moodle (sem portal, sem SSO, sem Playwright)
e consulta a API AJAX interna que o próprio front-end do Moodle usa.

Uso:  python3 probe_session.py

Só stdlib — não precisa de venv.
"""
import getpass
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://on.unoesc.edu.br"
TIMEOUT = 30
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [("User-Agent", UA)]


def get(url: str) -> str:
    with opener.open(url, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def post(url: str, data: dict) -> tuple[str, str]:
    body = urllib.parse.urlencode(data).encode()
    with opener.open(urllib.request.Request(url, data=body), timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace"), r.geturl()


def ajax(sesskey: str, methodname: str, args: dict):
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


def sesskey_of(html: str) -> str | None:
    m = re.search(r'"sesskey":"([^"]+)"', html)
    return m.group(1) if m else None


def main() -> int:
    user = input("Usuário do Moodle: ").strip()
    pwd = getpass.getpass("Senha: ")

    # ---- 1. login form ---------------------------------------------------
    print("\n[1] GET /login/index.php  (pegando logintoken)")
    page = get(f"{BASE}/login/index.php")
    m = re.search(r'name="logintoken"\s+value="([^"]+)"', page)
    logintoken = m.group(1) if m else ""
    print(f"    logintoken={'ok' if logintoken else 'AUSENTE'}")

    print("[2] POST /login/index.php")
    html, final = post(f"{BASE}/login/index.php", {
        "username": user, "password": pwd,
        "logintoken": logintoken, "anchor": "",
    })
    if "loginerrors" in html or "Dados de acesso inv" in html or "login/index.php" in final:
        # tenta detectar se ainda estamos na tela de login
        if re.search(r'name="logintoken"', html):
            print("    ✗ LOGIN RECUSADO — continuamos na tela de login")
            err = re.search(r'(?is)alert[^>]*>(.*?)</', html)
            if err:
                print("      motivo:", re.sub(r"<[^>]+>", " ", err.group(1)).strip()[:200])
            print("\n=> A senha do portal NÃO serve pro login direto do Moodle.")
            print("   Resta: SSO via portal (Playwright) para abrir sessão + AJAX,")
            print("   ou o .ics gerado manualmente uma vez.")
            return 1

    sesskey = sesskey_of(html)
    print(f"    ✓ LOGADO — url={final}")
    print(f"    sesskey={'ok' if sesskey else 'AUSENTE'}")
    cookies = [c.name for c in jar]
    print(f"    cookies={cookies}")

    if not sesskey:
        home = get(f"{BASE}/my/")
        sesskey = sesskey_of(home)
        print(f"    sesskey (via /my/)={'ok' if sesskey else 'AUSENTE'}")
    if not sesskey:
        print("    ✗ sem sesskey, não dá pra chamar o AJAX")
        return 1

    # nome do usuário logado, só pra confirmar
    who = re.search(r'"fullname":"([^"]*)"', html) or re.search(r"userId\":(\d+)", html)
    if who:
        print(f"    identidade: {who.group(1)}")

    # ---- 3. disciplinas --------------------------------------------------
    print("\n[3] core_course_get_enrolled_courses_by_timeline_classification")
    courses = []
    try:
        data = ajax(sesskey, "core_course_get_enrolled_courses_by_timeline_classification",
                    {"offset": 0, "limit": 0, "classification": "all",
                     "sort": "fullname", "customfieldname": "", "customfieldvalue": ""})
        courses = (data or {}).get("courses", [])
        print(f"    ✓ {len(courses)} disciplinas")
        for c in courses[:15]:
            print(f"        [{c.get('id')}] {c.get('shortname')} — {c.get('fullname')}")
    except Exception as exc:
        print(f"    ✗ {exc}")

    # ---- 4. calendário ---------------------------------------------------
    print("\n[4] core_calendar_get_action_events_by_timesort")
    try:
        data = ajax(sesskey, "core_calendar_get_action_events_by_timesort",
                    {"limitnum": 30, "timesortfrom": int(time.time()) - 86400 * 30,
                     "limittononsuspendedevents": True})
        events = (data or {}).get("events", [])
        print(f"    ✓ {len(events)} eventos")
        for e in events[:15]:
            course = (e.get("course") or {}).get("shortname", "")
            print(f"        {e.get('formattedtime', '')[:60]}")
            print(f"          {e.get('modulename', '?'):8} {e.get('name')}  [{course}]")
            print(f"          {e.get('url', '')}")
    except Exception as exc:
        print(f"    ✗ {exc}")

    # ---- 5. URL de assinatura .ics ---------------------------------------
    print("\n[5] /calendar/export.php — URL de assinatura")
    try:
        exp = get(f"{BASE}/calendar/export.php")
        tok = re.search(r"authtoken=([A-Za-z0-9]+)", exp)
        if tok:
            print(f"    ✓ authtoken encontrado na página: …{tok.group(1)[-6:]}")
        else:
            print("    · a página exige clicar em 'Exportar' pra gerar; "
                  "form presente:", bool(re.search(r"export_execute", exp)))
    except Exception as exc:
        print(f"    ✗ {exc}")

    print("\n=> Se [3] e [4] trouxeram dados, o Playwright inteiro pode morrer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
