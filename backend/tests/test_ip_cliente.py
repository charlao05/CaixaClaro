"""IP do cliente atrás do Caddy e do Cloudflare Tunnel (revisão de
2026-10-09, achado R10).

Antes: a API usava `request.client.host`, que em produção é sempre o
contêiner do Caddy. O limite de tentativas tratava todos como um só: o
sexto cadastro da hora, de qualquer pessoa, recebia 429.
"""
import random

from starlette.requests import Request

from caixaclaro.security.ip_cliente import ip_do_cliente

CADDY = "172.18.0.5"          # contêiner `web` na rede do compose
CONECTOR = "172.18.0.1"       # cloudflared no host, visto pelo Caddy
CLIENTE = "203.0.113.7"       # quem acessou o site (documentação, RFC 5737)
INVASOR = "198.51.100.23"     # alguém que acessou o servidor direto


def _req(peer: str | None, **cabecalhos: str) -> Request:
    headers = [
        (nome.replace("_", "-").lower().encode(), valor.encode())
        for nome, valor in cabecalhos.items()
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": headers,
        "client": (peer, 5000) if peer else None,
    }
    return Request(scope)


def test_sem_cabecalho_do_caddy_vale_a_conexao_direta():
    assert ip_do_cliente(_req("127.0.0.1")) == "127.0.0.1"
    assert ip_do_cliente(_req(None)) == "desconhecido"


def test_pelo_tunnel_vale_o_ip_que_a_cloudflare_informa():
    r = _req(CADDY, x_caixaclaro_conexao=CONECTOR, cf_connecting_ip=CLIENTE)
    assert ip_do_cliente(r) == CLIENTE


def test_pelo_tunnel_sem_cabecalho_da_cloudflare_vale_o_conector():
    assert ip_do_cliente(_req(CADDY, x_caixaclaro_conexao=CONECTOR)) == CONECTOR
    r = _req(CADDY, x_caixaclaro_conexao=CONECTOR, cf_connecting_ip="nao-e-ip")
    assert ip_do_cliente(r) == CONECTOR


def test_acesso_direto_ao_servidor_nao_consegue_forjar_o_ip():
    # Sem passar pela Cloudflare, o Caddy escreve o IP público do invasor;
    # o CF-Connecting-IP que ele mandou é ignorado.
    r = _req(CADDY, x_caixaclaro_conexao=INVASOR, cf_connecting_ip=CLIENTE)
    assert ip_do_cliente(r) == INVASOR


def test_api_exposta_direto_ignora_os_cabecalhos():
    r = _req(INVASOR, x_caixaclaro_conexao=CONECTOR, cf_connecting_ip=CLIENTE)
    assert ip_do_cliente(r) == INVASOR


def test_cabecalho_do_caddy_invalido_e_ignorado():
    r = _req(CADDY, x_caixaclaro_conexao="lixo", cf_connecting_ip=CLIENTE)
    assert ip_do_cliente(r) == CADDY


def test_endereco_ipv4_mapeado_em_ipv6_conta_como_interno():
    r = _req("::ffff:172.18.0.5", x_caixaclaro_conexao="::ffff:172.18.0.1",
             cf_connecting_ip=CLIENTE)
    assert ip_do_cliente(r) == CLIENTE


def test_ipv6_e_lista_de_enderecos():
    r = _req(CADDY, x_caixaclaro_conexao="::1", cf_connecting_ip="2001:db8::1, 10.0.0.1")
    assert ip_do_cliente(r) == "2001:db8::1"
    r = _req(CADDY, x_caixaclaro_conexao="2001:db8::99", cf_connecting_ip=CLIENTE)
    assert ip_do_cliente(r) == "2001:db8::99"


# ---------------------------------------------------------------------------
# Pela API: o limite de cadastro passa a ser por pessoa, não pelo Caddy
# ---------------------------------------------------------------------------

def _cpf() -> str:
    n = [random.randint(0, 9) for _ in range(9)]
    for _ in range(2):
        s = sum(d * (len(n) + 1 - i) for i, d in enumerate(n))
        r = s % 11
        n.append(0 if r < 2 else 11 - r)
    return "".join(map(str, n))


async def _cadastrar(client, i, cf_ip):
    return await client.post(
        "/api/v1/auth/register",
        headers={"X-CaixaClaro-Conexao": CONECTOR, "CF-Connecting-IP": cf_ip},
        json={"email": f"ip{i}@x.com", "senha": "senha12345", "cpf": _cpf()},
    )


async def test_seis_pessoas_diferentes_se_cadastram_na_mesma_hora(client):
    for i in range(6):
        r = await _cadastrar(client, i, f"203.0.113.{10 + i}")
        assert r.status_code == 201, (i, r.json())


async def test_a_mesma_pessoa_continua_limitada(client):
    codigos = [(await _cadastrar(client, i, CLIENTE)).status_code for i in range(6)]
    assert codigos == [201, 201, 201, 201, 201, 429]


async def test_auditoria_registra_o_ip_do_cliente(client):
    from caixaclaro.db import conexao

    r = await client.post(
        "/api/v1/auth/register",
        headers={"X-CaixaClaro-Conexao": CONECTOR, "CF-Connecting-IP": CLIENTE},
        json={"email": "ipaudit@x.com", "senha": "senha12345", "cpf": _cpf()},
    )
    assert r.status_code == 201, r.json()
    r = await client.post(
        "/api/v1/auth/login",
        headers={"X-CaixaClaro-Conexao": CONECTOR, "CF-Connecting-IP": CLIENTE},
        json={"email": "ipaudit@x.com", "senha": "senha12345"},
    )
    assert r.status_code == 200, r.json()
    async with conexao() as conn:
        ips = await conn.fetch(
            "SELECT DISTINCT meta->>'ip' AS ip FROM audit_log WHERE meta ? 'ip'"
        )
    assert {r["ip"] for r in ips} == {CLIENTE}
