#!/usr/bin/env python3
"""
Sonda a API do Moodle da UNOESC com credenciais reais.

Uso:  python3 probe_moodle.py
      (pede usuário e senha; a senha não aparece na tela)

NÃO imprime o token completo — só um trecho mascarado. O token cheio é
gravado em ./moodle_token.txt para você reaproveitar; apague depois.
"""
import getpass
import json
import sys
import urllib.parse
import urllib.request

BASE = "https://on.unoesc.edu.br"
TIMEOUT = 30

# Serviços que valem tentar, na ordem
SERVICES = ["moodle_mobile_app", "local_mobile"]


def post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "probe/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def ws(token: str, fn: str, **params) -> dict:
    data = {"wstoken": token, "wsfunction": fn, "moodlewsrestformat": "json", **params}
    return post(f"{BASE}/webservice/rest/server.php", data)


def mask(t: str) -> str:
    return f"{t[:4]}…{t[-4:]} ({len(t)} chars)" if len(t) > 10 else "???"


def main() -> int:
    user = input("Usuário do Moodle: ").strip()
    pwd = getpass.getpass("Senha: ")

    # ---- 1. tenta obter token -------------------------------------------
    token = None
    for svc in SERVICES:
        print(f"\n[1] /login/token.php  service={svc}")
        try:
            res = post(f"{BASE}/login/token.php",
                       {"username": user, "password": pwd, "service": svc})
        except Exception as exc:
            print(f"    ✗ falha de rede: {exc}")
            continue

        if "token" in res:
            token = res["token"]
            print(f"    ✓ TOKEN OBTIDO: {mask(token)}")
            break

        code = res.get("errorcode", "?")
        print(f"    ✗ {code}: {res.get('error', res)}")
        if code == "invalidlogin":
            print("      → usuário/senha não valem no login local do Moodle")
            print("        (pode ser que sua senha do portal seja diferente aqui)")
        elif code == "enabledservice":
            print("      → credencial OK, mas ESSE serviço está desabilitado")

    if not token:
        print("\n=> Sem token. O caminho REST está fechado pra você; "
              "restam o /lib/ajax/service.php (com sessão) e o .ics.")
        return 1

    with open("moodle_token.txt", "w") as fh:
        fh.write(token + "\n")
    print("    (token completo salvo em ./moodle_token.txt — apague depois)")

    # ---- 2. quem sou eu / o que posso chamar -----------------------------
    print("\n[2] core_webservice_get_site_info")
    info = ws(token, "core_webservice_get_site_info")
    if "exception" in info:
        print(f"    ✗ {info}")
        return 1
    uid = info.get("userid")
    print(f"    ✓ {info.get('fullname')}  userid={uid}")
    print(f"      site={info.get('sitename')}  release={info.get('release')}")

    funcs = sorted(f["name"] for f in info.get("functions", []))
    print(f"      {len(funcs)} funções liberadas")
    interesse = [f for f in funcs if any(
        k in f for k in ("calendar", "enrol_get_users_courses", "course_get_contents",
                         "assign_get_assignments", "quiz_get", "get_courses_by_field"))]
    print("      relevantes pra agenda:")
    for f in interesse:
        print(f"        - {f}")

    # ---- 3. disciplinas --------------------------------------------------
    print("\n[3] core_enrol_get_users_courses")
    try:
        courses = ws(token, "core_enrol_get_users_courses", userid=uid)
        if isinstance(courses, list):
            print(f"    ✓ {len(courses)} disciplinas")
            for c in courses[:10]:
                print(f"        [{c.get('id')}] {c.get('fullname')}")
        else:
            print(f"    ✗ {courses}")
    except Exception as exc:
        print(f"    ✗ {exc}")

    # ---- 4. calendário ---------------------------------------------------
    print("\n[4] core_calendar_get_action_events_by_timesort")
    try:
        ev = ws(token, "core_calendar_get_action_events_by_timesort",
                **{"timesortfrom": 0, "limitnum": 20})
        events = ev.get("events", []) if isinstance(ev, dict) else []
        if events:
            print(f"    ✓ {len(events)} eventos")
            for e in events[:10]:
                print(f"        {e.get('formattedtime', '')[:40]:42} | "
                      f"{e.get('name')}  ({(e.get('course') or {}).get('shortname', '')})")
        else:
            print(f"    · nenhum evento / resposta: {str(ev)[:300]}")
    except Exception as exc:
        print(f"    ✗ {exc}")

    # ---- 5. atividades de um curso --------------------------------------
    print("\n[5] core_course_get_contents (1º curso)")
    try:
        if isinstance(courses, list) and courses:
            cid = courses[0]["id"]
            secs = ws(token, "core_course_get_contents", courseid=cid)
            mods = [m for s in secs if isinstance(s, dict) for m in s.get("modules", [])]
            print(f"    ✓ curso {cid}: {len(secs)} seções, {len(mods)} atividades")
            for m in mods[:8]:
                print(f"        {m.get('modname'):10} {m.get('name')}")
    except Exception as exc:
        print(f"    ✗ {exc}")

    print("\n=> Se [3] e [4] vieram com dados, o Playwright pode morrer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
