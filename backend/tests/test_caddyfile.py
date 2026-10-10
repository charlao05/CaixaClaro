"""Caddyfile — o que a API e o monitor externo exigem do Caddy.

Duas coisas do backend só valem se o Caddyfile da raiz do repositório
continuar fazendo a parte dele:

  - `security/ip_cliente.py` (R10, DR7) confia no cabeçalho
    `X-CaixaClaro-Conexao`. Isso só é seguro se o Caddy escrever esse
    cabeçalho com o endereço de quem abriu a conexão com ele, substituindo
    qualquer valor mandado pelo cliente.
  - O monitor externo de `/readyz` (M10.C) só enxerga a API se `/readyz`
    for encaminhado a ela. Um caminho que não é encaminhado cai no front,
    que responde 200 com HTML para qualquer endereço — o monitor veria
    "tudo bem" com a API fora.

Duas camadas de teste:

  1. Leitura do arquivo — roda sempre.
  2. Caddy de verdade — roda quando há um binário (variável `CADDY_BIN` ou
     `caddy` no PATH). O CI baixa um; ver .github/workflows/backend-tests.yml.

Por que a camada 2 compara as duas grafias do endereço: em 2026-10-10 a
grafia curta `{remote_host}` foi trocada à mão no servidor pela longa
`{http.request.remote.host}`, na crença de que só a longa funcionava. São a
mesma coisa: o adaptador do Caddyfile troca a curta pela longa antes de
montar a configuração (docs/DECISOES.md, 2026-10-10).
"""
import http.client
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from caixaclaro.security.ip_cliente import CABECALHO_CONEXAO

CADDYFILE = Path(__file__).resolve().parents[2] / "Caddyfile"

GRAFIA_CURTA = "{remote_host}"
GRAFIA_LONGA = "{http.request.remote.host}"

CABECALHOS_DE_SEGURANCA = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}

pytestmark = pytest.mark.skipif(
    not CADDYFILE.is_file(),
    reason="Caddyfile fora do alcance (testes rodando sem a raiz do repositório)",
)


# ---------------------------------------------------------------------------
# Camada 1 — leitura do arquivo
# ---------------------------------------------------------------------------

def _diretivas(texto: str) -> list[tuple[tuple[str, ...], list[str]]]:
    """[(blocos em que a linha está, palavras da linha)].

    No Caddyfile um bloco abre com `{` sozinho no fim da linha e fecha com
    `}` sozinho na linha; `{nome}` colado é um marcador, não um bloco.
    """
    saida: list[tuple[tuple[str, ...], list[str]]] = []
    pilha: list[str] = []
    for bruta in texto.splitlines():
        linha = bruta.split("#", 1)[0].strip()
        if not linha:
            continue
        if linha == "}":
            pilha.pop()
            continue
        palavras = linha.split()
        abre = palavras[-1] == "{"
        if abre:
            palavras = palavras[:-1]
        if palavras:
            saida.append((tuple(pilha), palavras))
        if abre:
            pilha.append(" ".join(palavras))
    assert pilha == [], f"bloco sem fechar no Caddyfile: {pilha}"
    return saida


def test_cabecalho_de_conexao_e_escrito_dentro_do_proxy_com_o_endereco_do_par():
    diretivas = _diretivas(CADDYFILE.read_text(encoding="utf-8"))
    escritas = [
        (blocos, palavras)
        for blocos, palavras in diretivas
        if palavras[0] == "header_up"
        and len(palavras) >= 2
        and palavras[1].lower() == CABECALHO_CONEXAO
    ]
    assert len(escritas) == 1, (
        "o Caddyfile precisa escrever o cabeçalho de conexão exatamente uma vez"
    )
    blocos, palavras = escritas[0]
    assert blocos and blocos[-1].startswith("reverse_proxy "), blocos
    # header_up NOME VALOR substitui o que o cliente mandou. Com "+NOME" o
    # valor forjado seria mantido ao lado do verdadeiro.
    assert palavras[1:] in (
        [palavras[1], GRAFIA_CURTA],
        [palavras[1], GRAFIA_LONGA],
    ), palavras


def test_rotas_de_saude_sao_encaminhadas_para_a_api():
    diretivas = _diretivas(CADDYFILE.read_text(encoding="utf-8"))
    seletor = next(p for _, p in diretivas if p[:2] == ["@backend", "path"])
    for caminho in ("/api/*", "/healthz", "/readyz"):
        assert caminho in seletor, f"{caminho} precisa ir para a API"
    proxy = [b for b, p in diretivas if p[0] == "reverse_proxy"]
    assert proxy == [(":80", "handle @backend")], proxy


# ---------------------------------------------------------------------------
# Camada 2 — Caddy de verdade
# ---------------------------------------------------------------------------

def _caddy() -> str:
    binario = os.environ.get("CADDY_BIN") or shutil.which("caddy")
    if not binario:
        pytest.skip("sem binário do Caddy (defina CADDY_BIN para rodar)")
    return binario


def _env(tmp_path: Path) -> dict:
    return {
        **os.environ,
        "XDG_DATA_HOME": str(tmp_path / "xdg-data"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg-config"),
    }


def _adaptar(caddy: str, texto: str, pasta: Path) -> dict:
    """Configuração que o Caddy monta a partir do texto de um Caddyfile."""
    pasta.mkdir(parents=True)
    (pasta / "Caddyfile").write_text(texto, encoding="utf-8")
    r = subprocess.run(
        [caddy, "adapt", "--config", "Caddyfile", "--adapter", "caddyfile"],
        cwd=pasta, env=_env(pasta), capture_output=True, text=True, timeout=30,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _achar(no, chave: str) -> list:
    """Todos os valores guardados sob `chave`, em qualquer profundidade."""
    achados = []
    if isinstance(no, dict):
        for k, v in no.items():
            if k == chave:
                achados.append(v)
            achados.extend(_achar(v, chave))
    elif isinstance(no, list):
        for v in no:
            achados.extend(_achar(v, chave))
    return achados


def test_as_duas_grafias_do_endereco_geram_a_mesma_configuracao(tmp_path):
    caddy = _caddy()
    original = CADDYFILE.read_text(encoding="utf-8")
    usada = GRAFIA_CURTA if GRAFIA_CURTA in original else GRAFIA_LONGA
    outra = GRAFIA_LONGA if usada == GRAFIA_CURTA else GRAFIA_CURTA
    assert original.count(usada) == 1

    do_repo = _adaptar(caddy, original, tmp_path / "repo")
    trocada = _adaptar(caddy, original.replace(usada, outra), tmp_path / "trocada")

    assert do_repo == trocada

    # E o que fica na configuração é sempre a forma longa, numa escrita que
    # substitui ("set"), nunca que acrescenta ("add").
    pedidos = [h["request"] for h in _achar(do_repo, "headers") if "request" in h]
    assert pedidos == [{"set": {"X-Caixaclaro-Conexao": [GRAFIA_LONGA]}}], pedidos


class _Eco(BaseHTTPRequestHandler):
    """Faz o papel da API: guarda o que recebeu e responde 200."""

    vistos: ClassVar[list[dict]] = []

    def _responder(self):
        type(self).vistos.append({
            "metodo": self.command,
            "caminho": self.path,
            "conexao": self.headers.get_all(CABECALHO_CONEXAO) or [],
        })
        corpo = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    do_GET = _responder
    do_HEAD = _responder

    def log_message(self, *args):  # silencioso
        pass


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _trocar_uma_vez(texto: str, antigo: str, novo: str) -> str:
    assert texto.count(antigo) == 1, f"esperava achar uma vez: {antigo!r}"
    return texto.replace(antigo, novo)


@pytest.fixture
def caddy_no_ar(tmp_path):
    """Sobe o Caddy com o Caddyfile do repositório. Só mudam a porta de
    escuta, o endereço da API e a pasta do front, que no servidor são
    `:80`, `api:8000` e `/srv/frontend`."""
    caddy = _caddy()
    _Eco.vistos = []
    api = ThreadingHTTPServer(("127.0.0.1", 0), _Eco)
    threading.Thread(target=api.serve_forever, daemon=True).start()

    front = tmp_path / "front"
    front.mkdir()
    (front / "index.html").write_text("<title>front de teste</title>")

    porta = _porta_livre()
    texto = CADDYFILE.read_text(encoding="utf-8")
    texto = _trocar_uma_vez(texto, ":80 {", f":{porta} {{")
    texto = _trocar_uma_vez(
        texto, "reverse_proxy api:8000", f"reverse_proxy 127.0.0.1:{api.server_port}"
    )
    texto = _trocar_uma_vez(texto, "root * /srv/frontend", f"root * {front}")
    # Sem a porta de administração (2019), para não colidir com outro Caddy.
    (tmp_path / "Caddyfile").write_text("{\n    admin off\n}\n" + texto)

    processo = subprocess.Popen(
        [caddy, "run", "--config", "Caddyfile", "--adapter", "caddyfile"],
        cwd=tmp_path, env=_env(tmp_path),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        limite = time.monotonic() + 15
        while True:
            try:
                socket.create_connection(("127.0.0.1", porta), timeout=0.5).close()
                break
            except OSError:
                assert processo.poll() is None, "o Caddy encerrou ao subir"
                assert time.monotonic() < limite, "o Caddy não abriu a porta"
                time.sleep(0.1)
        yield porta
    finally:
        processo.terminate()
        processo.wait(timeout=10)
        api.shutdown()
        api.server_close()


def _pedir(porta: int, metodo: str, caminho: str, cabecalhos: dict | None = None):
    conexao = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    try:
        conexao.request(metodo, caminho, headers=cabecalhos or {})
        resposta = conexao.getresponse()
        corpo = resposta.read()
        return resposta.status, {k.lower(): v for k, v in resposta.getheaders()}, corpo
    finally:
        conexao.close()


def test_cabecalho_de_conexao_forjado_chega_substituido(caddy_no_ar):
    porta = caddy_no_ar

    status, _, _ = _pedir(porta, "GET", "/api/v1/qualquer")
    assert status == 200
    assert _Eco.vistos[-1]["conexao"] == ["127.0.0.1"]

    # Quem acessa tenta se passar por conexão vinda de outro endereço.
    for nome in ("X-CaixaClaro-Conexao", "x-caixaclaro-conexao"):
        status, _, _ = _pedir(porta, "GET", "/api/v1/qualquer", {nome: "8.8.8.8"})
        assert status == 200
        assert _Eco.vistos[-1]["conexao"] == ["127.0.0.1"], nome


def test_readyz_chega_na_api_com_o_metodo_que_o_monitor_usou(caddy_no_ar):
    porta = caddy_no_ar
    for metodo in ("GET", "HEAD"):
        status, cabecalhos, corpo = _pedir(porta, metodo, "/readyz")
        assert status == 200
        # O Caddy não troca HEAD por GET: é a API que precisa responder a HEAD.
        assert _Eco.vistos[-1]["metodo"] == metodo
        assert _Eco.vistos[-1]["caminho"] == "/readyz"
        assert corpo == (b"" if metodo == "HEAD" else b'{"ok":true}')
        for nome, valor in CABECALHOS_DE_SEGURANCA.items():
            assert cabecalhos.get(nome) == valor, (metodo, nome)


def test_caminho_que_nao_e_da_api_recebe_o_front_e_nao_chega_na_api(caddy_no_ar):
    """É por isto que o monitor externo deve conferir o corpo (`"ok":true`)
    e não só o código 200: o front responde 200 a qualquer endereço."""
    porta = caddy_no_ar
    antes = len(_Eco.vistos)
    status, cabecalhos, corpo = _pedir(porta, "GET", "/pagina-do-app")
    assert status == 200
    assert b"front de teste" in corpo
    assert len(_Eco.vistos) == antes
    for nome, valor in CABECALHOS_DE_SEGURANCA.items():
        assert cabecalhos.get(nome) == valor, nome
