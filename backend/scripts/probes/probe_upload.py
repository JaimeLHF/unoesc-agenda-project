#!/usr/bin/env python3
"""
Prova a primeira metade do envio: subir um arquivo para a área de rascunho.

Rascunho não é envio. O arquivo vai para a gaveta pessoal do aluno no Moodle
(`draft`), que é onde o seletor de arquivos guarda o que ainda não foi salvo na
tarefa. Enquanto ninguém fizer `savesubmission`, a tarefa continua exatamente
como está — e este probe **não faz** `savesubmission`.

Para não deixar sujeira, ele ainda lista o rascunho e apaga o que subiu.

Uso:  python3 probe_upload.py

Só stdlib — não precisa de venv.
"""
import getpass
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request
import uuid

BASE = "https://on.unoesc.edu.br"
TIMEOUT = 60
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


def post_multipart(url: str, campos: dict, arquivo: tuple[str, bytes, str]) -> str:
    """POST `multipart/form-data` na mão — o upload do Moodle não aceita outro."""
    limite = "----agenda" + uuid.uuid4().hex
    partes = []
    for chave, valor in campos.items():
        partes.append(
            f"--{limite}\r\nContent-Disposition: form-data; name=\"{chave}\"\r\n\r\n{valor}\r\n"
            .encode()
        )
    nome_campo, conteudo, nome_arquivo = arquivo
    partes.append(
        f"--{limite}\r\nContent-Disposition: form-data; name=\"{nome_campo}\"; "
        f"filename=\"{nome_arquivo}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
        + conteudo + b"\r\n"
    )
    partes.append(f"--{limite}--\r\n".encode())
    corpo = b"".join(partes)

    req = urllib.request.Request(url, data=corpo, headers={
        "Content-Type": f"multipart/form-data; boundary={limite}",
    })
    with opener.open(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def campos_ocultos(html: str) -> dict:
    saida = {}
    for tag in re.findall(r"<input[^>]*type=[\"']hidden[\"'][^>]*>", html):
        n = re.search(r"name=[\"']([^\"']+)[\"']", tag)
        v = re.search(r"value=[\"']([^\"']*)[\"']", tag)
        if n:
            saida[n.group(1)] = v.group(1) if v else ""
    return saida


def main() -> int:
    user = input("Usuário do Moodle: ").strip()
    pwd = getpass.getpass("Senha: ")
    cmid = input("id da tarefa (o `id=` da URL, ex.: 71688): ").strip()

    page = get(f"{BASE}/login/index.php")
    m = re.search(r'name="logintoken"\s+value="([^"]+)"', page)
    html = post(f"{BASE}/login/index.php", {
        "username": user, "password": pwd,
        "logintoken": m.group(1) if m else "", "anchor": "",
    })
    if re.search(r'name="logintoken"', html):
        print("✗ login recusado")
        return 1
    ms = re.search(r'"sesskey":"([^"]+)"', html) or re.search(
        r'"sesskey":"([^"]+)"', get(f"{BASE}/my/"))
    sesskey = ms.group(1) if ms else ""
    print(f"✓ logado — sesskey={'ok' if sesskey else 'AUSENTE'}")

    # ---- 1. o formulário, que dá o rascunho e o contexto ------------------
    form = get(f"{BASE}/mod/assign/view.php?id={cmid}&action=editsubmission")
    ocultos = campos_ocultos(form)
    itemid = ocultos.get("files_filemanager")
    print(f"\n[1] itemid do rascunho de arquivos: {itemid or 'não achei'}")
    if not itemid:
        print("    · esta tarefa não aceita arquivo (só texto online?) — nada a testar")
        return 1

    ctx = re.search(r'"contextid"\s*:\s*(\d+)', form) \
        or re.search(r'"context"\s*:\s*\{\s*"id"\s*:\s*(\d+)', form) \
        or re.search(r'contextid=(\d+)', form)
    ctx_id = ctx.group(1) if ctx else None
    print(f"    ctx_id: {ctx_id or 'não achei'}")

    repo = None
    for m_up in re.finditer(r'"type"\s*:\s*"upload"', form):
        ids = re.findall(r'"id"\s*:\s*"?(\d+)"?', form[max(0, m_up.start() - 400):m_up.start()])
        if ids:
            repo = ids[-1]
            break
    print(f"    repo_id de upload: {repo or 'não achei'}")
    if not (ctx_id and repo):
        print("    · sem ctx_id ou repo_id não dá para subir; cole esta saída no chat")
        return 1

    # ---- 2. sobe um arquivo de teste para o rascunho ----------------------
    nome = "teste-agenda-unoesc.txt"
    conteudo = b"Arquivo de teste do app Agenda UNOESC. Pode apagar.\n"
    print(f"\n[2] POST /repository/repository_ajax.php?action=upload  ({nome})")
    try:
        bruto = post_multipart(
            f"{BASE}/repository/repository_ajax.php?action=upload",
            {
                "sesskey": sesskey,
                "repo_id": repo,
                "itemid": itemid,
                "ctx_id": ctx_id,
                "author": "",
                "savepath": "/",
                "title": nome,
                "license": "unknown",
                "overwrite": "1",
            },
            ("repo_upload_file", conteudo, nome),
        )
        print("    resposta:", bruto[:400])
    except Exception as exc:
        print(f"    ✗ {exc}")
        return 1

    # ---- 3. confere e limpa ----------------------------------------------
    print("\n[3] listando o rascunho")
    try:
        lista = post(f"{BASE}/repository/draftfiles_ajax.php?action=list", {
            "sesskey": sesskey, "client_id": "agenda", "itemid": itemid,
            "filepath": "/", "draftpath": "/",
        })
        dados = json.loads(lista)
        for f in dados.get("list", []):
            print(f"      {f.get('filename')}  {f.get('size')} bytes")
    except Exception as exc:
        print(f"    · não consegui listar: {str(exc)[:120]}")

    print("\n[4] apagando o arquivo de teste do rascunho")
    try:
        apagou = post(f"{BASE}/repository/draftfiles_ajax.php?action=delete", {
            "sesskey": sesskey, "client_id": "agenda", "itemid": itemid,
            "filepath": "/", "filename": nome,
        })
        print("    resposta:", apagou[:200])
    except Exception as exc:
        print(f"    · não consegui apagar: {str(exc)[:120]}")

    print("\n=> Se [2] devolveu um JSON com o arquivo, o upload pelo app funciona.")
    print("   A tarefa NÃO foi tocada: nenhum savesubmission foi feito.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
