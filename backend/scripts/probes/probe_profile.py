#!/usr/bin/env python3
"""
Descobre o que o Moodle entrega sobre o próprio aluno — matéria-prima da tela
de perfil.

O mesmo método dos outros probes: medir antes de escrever o parser. Aqui
importa saber quais campos existem de verdade nesta instância (`/user/edit.php`
é a fonte mais rica, porque é o form que o próprio aluno preenche) e quais
funções AJAX de perfil/notas estão ligadas.

Uso:  python3 probe_profile.py

Só stdlib — não precisa de venv. Os valores aparecem truncados na tela; é a
sua própria conta, mas o objetivo é ver o NOME dos campos, não colecionar dado.
"""
import getpass
import html as html_mod
import http.cookiejar
import json
import re
import sys
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


def post(url: str, data: dict) -> str:
    body = urllib.parse.urlencode(data).encode()
    with opener.open(urllib.request.Request(url, data=body), timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


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


def texto(s: str, limite: int = 60) -> str:
    s = html_mod.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limite]


def main() -> int:
    user = input("Usuário do Moodle: ").strip()
    pwd = getpass.getpass("Senha: ")

    # ---- login -----------------------------------------------------------
    page = get(f"{BASE}/login/index.php")
    m = re.search(r'name="logintoken"\s+value="([^"]+)"', page)
    html = post(f"{BASE}/login/index.php", {
        "username": user, "password": pwd,
        "logintoken": m.group(1) if m else "", "anchor": "",
    })
    if re.search(r'name="logintoken"', html):
        print("✗ login recusado")
        return 1

    ms = re.search(r'"sesskey":"([^"]+)"', html)
    sesskey = ms.group(1) if ms else None
    if not sesskey:
        html = get(f"{BASE}/my/")
        mm = re.search(r'"sesskey":"([^"]+)"', html)
        sesskey = mm.group(1) if mm else None
    print(f"✓ logado — sesskey={'ok' if sesskey else 'AUSENTE'}")

    mid = re.search(r'"userId":(\d+)', html) or re.search(r'"userid":(\d+)', html)
    userid = mid.group(1) if mid else None
    print(f"  userid={userid or 'não achei no M.cfg'}")

    # ---- 1. página de perfil --------------------------------------------
    print("\n[1] GET /user/profile.php  (o que a página mostra)")
    try:
        prof = get(f"{BASE}/user/profile.php")
        nome = re.search(r"<title>(.*?)</title>", prof, re.S)
        print(f"    title: {texto(nome.group(1)) if nome else '?'}")
        # O perfil do Moodle é uma lista de <dl>/<li> "rótulo: valor"
        pares = re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", prof, re.S)
        pares += re.findall(r'class="[^"]*profile_tree[^"]*".*?<h\d[^>]*>(.*?)</h\d>(.*?)</section>',
                            prof, re.S)
        if pares:
            for k, v in pares[:40]:
                print(f"      {texto(k, 30):32} = {texto(v)}")
        else:
            print("    · sem <dt>/<dd> — layout diferente; salvando amostra")
            print("      trecho:", texto(prof[:400], 300))
        foto = re.search(r'src="([^"]*pluginfile\.php[^"]*user/icon[^"]*)"', prof)
        print(f"    foto: {foto.group(1) if foto else 'não encontrada'}")
    except Exception as exc:
        print(f"    ✗ {exc}")

    # ---- 2. form de edição: a fonte mais completa ------------------------
    print("\n[2] GET /user/edit.php  (campos do form = tudo que o Moodle guarda)")
    try:
        edit = get(f"{BASE}/user/edit.php" + (f"?id={userid}" if userid else ""))
        campos = re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', edit)
        vistos = set()
        for nome_c, valor in campos:
            if nome_c in vistos or nome_c.startswith(("sesskey", "_qf", "mform")):
                continue
            vistos.add(nome_c)
            print(f"      {nome_c:32} = {texto(valor, 50)}")
        selects = re.findall(r'<select[^>]*name="([^"]+)"', edit)
        if selects:
            print(f"    selects: {', '.join(dict.fromkeys(selects))[:200]}")
    except Exception as exc:
        print(f"    ✗ {exc}")

    # ---- 3. funções AJAX candidatas -------------------------------------
    print("\n[3] funções AJAX de perfil / notas / progresso")
    tentativas = [
        ("core_user_get_users_by_field", {"field": "id", "values": [int(userid or 0)]}),
        ("core_webservice_get_site_info", {}),
        ("core_user_get_private_files_info", {}),
        ("gradereport_overview_get_course_grades", {}),
        ("core_course_get_user_navigation_options", {"courseids": []}),
    ]
    for fn, args in tentativas:
        if not sesskey:
            break
        try:
            data = ajax(sesskey, fn, args)
            amostra = json.dumps(data, ensure_ascii=False)[:300]
            print(f"    ✓ {fn}\n        {amostra}")
        except Exception as exc:
            print(f"    ✗ {fn}: {str(exc)[:120]}")

    print("\n=> Cole a saída no chat: os campos de [1]/[2] definem o que a tela "
          "de perfil consegue mostrar sem inventar dado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
