#!/usr/bin/env python3
"""
Descobre se prazos de fórum (hsuforum / forum) chegam ao calendário do Moodle.

Se um fórum tem "Data de entrega" na página mas o cmid dele não aparece em
nenhum evento do calendário, então o monthly_view SOZINHO perde eventos e o
MoodleClient precisa de uma segunda fonte.

Uso:  python3 probe_forums.py [meses_para_tras] [meses_para_frente]
      padrão: 3 12

Só stdlib.
"""
import getpass
import html as htmlmod
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

BASE = "https://on.unoesc.edu.br"
TIMEOUT = 40
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
TZ_BR = timezone(timedelta(hours=-3))
PAUSA = 0.15  # segundos entre requisições, pra não martelar o servidor

# Módulos que investigamos página a página
ALVOS = ("hsuforum", "forum")

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
    return datetime.fromtimestamp(int(ts), TZ_BR).strftime("%d/%m/%Y %H:%M") if ts else "-"


def limpa(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def login():
    user = input("Usuário do Moodle: ").strip()
    pwd = getpass.getpass("Senha: ")
    page = get(f"{BASE}/login/index.php")
    m = re.search(r'name="logintoken"\s+value="([^"]+)"', page)
    h, _ = post_form(f"{BASE}/login/index.php", {
        "username": user, "password": pwd,
        "logintoken": m.group(1) if m else "", "anchor": "",
    })
    if re.search(r'name="logintoken"', h):
        print("✗ login recusado")
        sys.exit(1)
    sk = re.search(r'"sesskey":"([^"]+)"', h) or re.search(r'"sesskey":"([^"]+)"', get(f"{BASE}/my/"))
    print("✓ logado\n")
    return sk.group(1)


def datas_da_pagina(html):
    """
    Extrai o bloco 'activity-dates' que o Moodle 4.x renderiza no topo da
    atividade. Devolve lista de (rótulo, texto_da_data).
    """
    achados = []
    bloco = re.search(r'(?is)<div[^>]*class="[^"]*activity-dates[^"]*"[^>]*>(.*?)</div>\s*</div>', html)
    trecho = bloco.group(1) if bloco else html
    for m in re.finditer(r'(?is)<strong>(.*?)</strong>\s*([^<]{4,60})', trecho):
        rot, val = limpa(m.group(1)), limpa(m.group(2))
        if rot and val and re.search(r"\d", val):
            achados.append((rot.rstrip(":"), val))
    if not achados:
        # fallback textual, sem depender de markup
        for m in re.finditer(
                r'(?i)(Data de entrega|Data limite|Data de corte|Prazo final|Encerra em|Vencimento)'
                r'[\s:]*([^<\n]{6,60})', html):
            achados.append((limpa(m.group(1)), limpa(m.group(2))))
    return achados[:4]


def main():
    # Janela larga por padrão: uma data de fórum pode ser de semestres passados,
    # e concluir "fora do calendário" olhando só alguns meses dá falso positivo.
    tras = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    frente = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    sesskey = login()

    # ---- 1. calendário: janela ampla, indexado por cmid ------------------
    print(f"[1] monthly_view — {tras} meses atrás até {frente} à frente")
    hoje = datetime.now(TZ_BR)
    eventos, cmids_com_evento = [], set()
    vistos = set()
    for i in range(-tras, frente + 1):
        ano = hoje.year + (hoje.month - 1 + i) // 12
        mes = (hoje.month - 1 + i) % 12 + 1
        try:
            d = ajax(sesskey, "core_calendar_get_calendar_monthly_view",
                     {"year": ano, "month": mes, "courseid": 1, "categoryid": 0,
                      "includenavigation": False, "mini": False})
            for w in (d or {}).get("weeks", []):
                for day in w.get("days", []):
                    for e in day.get("events", []):
                        if e.get("id") in vistos:
                            continue
                        vistos.add(e.get("id"))
                        eventos.append(e)
                        m = re.search(r"/mod/[a-z0-9_]+/view\.php\?id=(\d+)", e.get("url") or "")
                        if m:
                            cmids_com_evento.add(m.group(1))
        except Exception as exc:
            print(f"    {mes:02d}/{ano}: ✗ {exc}")
        time.sleep(PAUSA)

    por_mod = {}
    for e in eventos:
        k = e.get("modulename") or "-"
        por_mod[k] = por_mod.get(k, 0) + 1
    print(f"    → {len(eventos)} eventos únicos")
    print("    por módulo:", ", ".join(f"{v}x {k}" for k, v in sorted(por_mod.items(), key=lambda x: -x[1])))
    print(f"    cmids com evento: {len(cmids_com_evento)}")

    # ---- 2. enumera os fóruns das disciplinas ---------------------------
    d = ajax(sesskey, "core_course_get_enrolled_courses_by_timeline_classification",
             {"offset": 0, "limit": 0, "classification": "all", "sort": "fullname",
              "customfieldname": "", "customfieldvalue": ""})
    courses = (d or {}).get("courses", [])

    foruns = []  # (curso, modname, cmid, nome)
    print(f"\n[2] varrendo {len(courses)} disciplinas atrás de {'/'.join(ALVOS)}")
    for c in courses:
        page = get(f"{BASE}/course/view.php?id={c['id']}")
        time.sleep(PAUSA)
        for mod in ALVOS:
            # Só o link REAL da atividade traz <span class="instancename">.
            # Sem esse filtro, qualquer "clique aqui" na descrição de uma seção
            # apontando para o fórum entra como se fosse uma atividade.
            for m in re.finditer(
                    rf'(?is)<a[^>]+href="[^"]*/mod/{mod}/view\.php\?id=(\d+)[^"]*"[^>]*>(.*?)</a>', page):
                cmid, interno = m.group(1), m.group(2)
                if "instancename" not in interno:
                    continue
                nome = limpa(re.sub(r'(?is)<span class="accesshide".*?</span>', "", interno))
                if nome and not any(f[2] == cmid for f in foruns):
                    foruns.append((c.get("shortname", ""), mod, cmid, nome[:60]))
    print(f"    → {len(foruns)} fóruns encontrados (só links de atividade real)")

    # ---- 3. abre cada fórum e procura data ------------------------------
    print(f"\n[3] abrindo cada fórum ({len(foruns)} requisições, aguarde)\n")
    com_data, sem_data, com_data_sem_evento = [], [], []
    for curso, mod, cmid, nome in foruns:
        try:
            page = get(f"{BASE}/mod/{mod}/view.php?id={cmid}")
        except Exception as exc:
            print(f"    ✗ {mod}/{cmid}: {exc}")
            continue
        time.sleep(PAUSA)
        datas = datas_da_pagina(page)
        tem_evento = cmid in cmids_com_evento
        if datas:
            com_data.append((curso, mod, cmid, nome, datas, tem_evento))
            marca = "✓ no calendário" if tem_evento else "✗ FORA DO CALENDÁRIO"
            print(f"    [{mod}/{cmid}] {nome}")
            for rot, val in datas:
                print(f"        {rot}: {val}")
            print(f"        {marca}   ({curso})")
            if not tem_evento:
                com_data_sem_evento.append((curso, mod, cmid, nome, datas))
        else:
            sem_data.append((mod, cmid, nome, tem_evento))

    # ---- 4. veredito ----------------------------------------------------
    print("\n" + "=" * 72)
    print(f"fóruns analisados:            {len(foruns)}")
    print(f"  com data na página:         {len(com_data)}")
    print(f"  sem data nenhuma:           {len(sem_data)}")
    print(f"  com data MAS fora do calendário: {len(com_data_sem_evento)}")

    orfaos_no_calendario = [f for f in sem_data if f[3]]
    if orfaos_no_calendario:
        print(f"  sem data na página mas COM evento: {len(orfaos_no_calendario)}"
              "  (o parser de data falhou nesses)")

    print()
    if not com_data:
        print("→ Nenhum fórum tem prazo. O monthly_view não está perdendo nada:")
        print("  fórum aqui é discussão contínua, não entregável. Sem ponto cego.")
    elif not com_data_sem_evento:
        print("→ Todo fórum com prazo TAMBÉM está no calendário.")
        print("  O monthly_view sozinho basta. Sem ponto cego.")
    else:
        # Separa prazo vivo de entulho de semestre passado: um fórum de 2025
        # "fora do calendário" não é ponto cego, é atividade morta.
        ano_atual = hoje.year
        vivos, velhos = [], []
        for item in com_data_sem_evento:
            anos = [int(a) for a in re.findall(r"\b(20\d{2})\b", " ".join(v for _, v in item[4]))]
            (velhos if anos and max(anos) < ano_atual else vivos).append((item, anos))

        if velhos:
            print(f"→ {len(velhos)} fóruns com prazo de ano anterior — atividade antiga,")
            print("  não é ponto cego (a janela do calendário nem alcança):")
            for (curso, mod, cmid, nome, datas), anos in velhos[:10]:
                print(f"      [{mod}/{cmid}] {nome} — {datas[0][0]}: {datas[0][1]}")

        if not vivos:
            print("\n→ SEM PONTO CEGO: nenhum fórum com prazo vigente ficou fora do")
            print("  calendário. O monthly_view sozinho basta.")
        else:
            print(f"\n→ PONTO CEGO CONFIRMADO: {len(vivos)} fóruns com prazo VIGENTE")
            print("  que o calendário não mostra. O MoodleClient precisa de uma")
            print("  segunda fonte além do calendário. Os afetados:")
            for (curso, mod, cmid, nome, datas), _ in vivos[:15]:
                print(f"      [{mod}/{cmid}] {nome} — {datas[0][0]}: {datas[0][1]}")


if __name__ == "__main__":
    main()
