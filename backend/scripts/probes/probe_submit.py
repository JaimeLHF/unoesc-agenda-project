#!/usr/bin/env python3
"""
Descobre se dá para ENVIAR uma tarefa do Moodle pelo nosso app.

Este probe **não envia nada**. Ele abre a página de envio de uma tarefa e
mostra as peças que um envio de verdade precisaria: o formulário, o repositório
de upload, o rascunho (`itemid`) e as regras da tarefa (tipos aceitos, tamanho
máximo, quantos arquivos, se exige aceitar a declaração de autoria).

O caminho de um envio no Moodle tem duas etapas, e é isso que estamos medindo:

  1. `POST /repository/repository_ajax.php?action=upload` põe o arquivo numa
     área de rascunho do aluno (o `itemid` do formulário)
  2. `POST /mod/assign/view.php?action=savesubmission` amarra esse rascunho à
     tarefa; em muitas tarefas ainda falta o "enviar para avaliação", que é
     outro POST e costuma ser irreversível

Uso:  python3 probe_submit.py

Só stdlib — não precisa de venv.
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
    data = item.get("data")
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data
    return data


def texto(s: str, limite: int = 90) -> str:
    s = html_mod.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()[:limite]


def main() -> int:
    user = input("Usuário do Moodle: ").strip()
    pwd = getpass.getpass("Senha: ")

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
        ms = re.search(r'"sesskey":"([^"]+)"', html)
        sesskey = ms.group(1) if ms else None
    print(f"✓ logado — sesskey={'ok' if sesskey else 'AUSENTE'}")

    # ---- 1. acha tarefas (assign) nas disciplinas -------------------------
    print("\n[1] procurando tarefas nas suas disciplinas")
    cursos = (ajax(sesskey, "core_course_get_enrolled_courses_by_timeline_classification",
                   {"offset": 0, "limit": 0, "classification": "all", "sort": "fullname",
                    "customfieldname": "", "customfieldvalue": ""}) or {}).get("courses", [])
    tarefas = []
    for c in cursos:
        try:
            estado = ajax(sesskey, "core_courseformat_get_state", {"courseid": c.get("id")})
        except Exception:
            continue
        for cm in (estado or {}).get("cm", []):
            url = cm.get("url") or ""
            if "/mod/assign/" in url:
                tarefas.append((c.get("fullname", "")[:40], cm.get("name", "")[:50], url))
    print(f"    {len(tarefas)} tarefa(s) encontrada(s)")
    for i, (curso, nome, url) in enumerate(tarefas[:15]):
        print(f"      [{i}] {nome}  ({curso})")
    if not tarefas:
        print("    · sem tarefas — nada a medir")
        return 0

    escolha = input(f"\nQual tarefa abrir? [0-{min(len(tarefas), 15) - 1}] (Enter = 0): ").strip()
    idx = int(escolha) if escolha.isdigit() and int(escolha) < len(tarefas) else 0
    curso, nome, url = tarefas[idx]
    print(f"\n[2] GET {url}\n    {nome}")

    pagina = get(url)
    cmid = re.search(r"[?&]id=(\d+)", url)
    cmid = cmid.group(1) if cmid else "?"

    # Status atual: já enviou? ainda dá para editar?
    print("    status atual:")
    tabela = re.search(r'(?is)<table[^>]*generaltable.*?</table>', pagina)
    if tabela:
        for linha in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", tabela.group(0)):
            celulas = re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", linha)
            if len(celulas) == 2:
                print(f"      {texto(celulas[0], 32):34} = {texto(celulas[1], 70)}")

    botoes = re.findall(r'action=(editsubmission|submit|removesubmission)', pagina)
    print(f"    ações oferecidas na página: {sorted(set(botoes)) or 'nenhuma'}")

    # ---- 3. o formulário de envio ----------------------------------------
    print(f"\n[3] GET /mod/assign/view.php?id={cmid}&action=editsubmission")
    try:
        form = get(f"{BASE}/mod/assign/view.php?id={cmid}&action=editsubmission")
    except Exception as exc:
        print(f"    ✗ {exc}")
        return 1

    if "editsubmission" not in form and "filemanager" not in form:
        print("    · a página não abriu o formulário — talvez o envio esteja fechado")

    campos = re.findall(r'<input[^>]*type="hidden"[^>]*>', form)
    interessantes = {}
    for c in campos:
        n = re.search(r'name="([^"]+)"', c)
        v = re.search(r'value="([^"]*)"', c)
        if n and n.group(1) not in ("sesskey",):
            interessantes[n.group(1)] = (v.group(1) if v else "")[:40]
    print("    campos escondidos do formulário:")
    for k, v in list(interessantes.items())[:20]:
        print(f"      {k:34} = {v}")

    # O `itemid` do rascunho é o que liga o upload à submissão.
    item = re.search(r'name="files_filemanager"\s+value="(\d+)"', form) \
        or re.search(r'"itemid":(\d+)', form)
    print(f"    itemid do rascunho: {item.group(1) if item else 'não achei'}")

    # Repositório "upload" — o destino do POST do arquivo.
    repos = re.findall(r'"id":(\d+),"name":"([^"]*)","type":"([^"]*)"', form)
    up = [r for r in repos if r[2] == "upload"]
    print(f"    repositórios no seletor: {[(r[1], r[2]) for r in repos][:6] or 'não achei'}")
    print(f"    repo_id de upload: {up[0][0] if up else 'não achei'}")

    # Regras da tarefa: o que o professor permite enviar.
    for rotulo, padrao in [
        ("tipos aceitos", r'(?i)tipos de arquivo aceitos[^<]*<[^>]*>([^<]{0,120})'),
        ("tamanho máximo", r'(?i)(tamanho m[áa]ximo[^<]{0,60})'),
        ("máximo de arquivos", r'(?i)(n[úu]mero m[áa]ximo de arquivos[^<]{0,40})'),
        ("declaração de autoria", r'(?i)(submissionstatement|declaro que)'),
    ]:
        achado = re.search(padrao, form)
        print(f"    {rotulo}: {texto(achado.group(1)) if achado else '—'}")

    print("\n=> Com itemid + repo_id + os campos escondidos, o envio pelo app é")
    print("   possível. Cole a saída no chat para eu escrever o cliente.")
    print("   NADA foi enviado por este probe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
