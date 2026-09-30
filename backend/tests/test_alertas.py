"""Alertas — leitura e marcar-lido. GET /alertas, POST /{id}/lido."""
import uuid
from decimal import Decimal

from caixaclaro.db import conexao


async def _registrar(client, email="al@x.com", cpf="111.444.777-35"):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


def _key():
    return str(uuid.uuid4())


async def _colar(client, token, texto):
    return await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": texto},
    )


async def _criar_alerta_60(client, token):
    """Cola receita PJ que cruza 60% (R$ 50.000)."""
    r = await _colar(
        client, token,
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 50.000,00",
    )
    assert r.status_code == 201


# ============================================================
# GET /alertas
# ============================================================

async def test_alertas_vazio(client):
    token = await _registrar(client)
    r = await client.get(
        "/api/v1/transacoes/alertas",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["itens"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_alertas_lista_shape(client):
    token = await _registrar(client, email="al2@x.com", cpf="222.222.220-60")
    await _criar_alerta_60(client, token)

    r = await client.get(
        "/api/v1/transacoes/alertas",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    itens = r.json()["itens"]
    assert len(itens) >= 1
    a = itens[0]
    for campo in (
        "id", "tipo", "severidade", "mensagem",
        "lido_em", "criado_em", "banda_ou_slug", "prazo",
    ):
        assert campo in a, f"faltando: {campo}"
    assert a["tipo"] == "faturamento_faixa"
    assert a["banda_ou_slug"] == "enq_MEI_60"
    assert a["lido_em"] is None


async def test_alertas_apenas_nao_lidos(client):
    token = await _registrar(client, email="al3@x.com", cpf="333.333.330-90")
    await _criar_alerta_60(client, token)

    async with conexao() as conn:
        aid = await conn.fetchval(
            "SELECT id FROM alerts WHERE tipo = 'faturamento_faixa' LIMIT 1"
        )

    r = await client.post(
        f"/api/v1/transacoes/alertas/{aid}/lido",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()

    r = await client.get(
        "/api/v1/transacoes/alertas?apenas_nao_lidos=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["itens"] == []

    r = await client.get(
        "/api/v1/transacoes/alertas",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(r.json()["itens"]) >= 1


async def test_alertas_cursor_e_has_more(client):
    token = await _registrar(
        client,
        email="cur_alertas@x.com",
        cpf="303.303.303-22",
    )

    # R$ 100.000 cruza 60%, 80%, 90%, 95%, 100% e 120%:
    # gera 6 alertas pelo fluxo oficial de faturamento.
    r = await _colar(
        client,
        token,
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 100.000,00",
    )
    assert r.status_code == 201, r.json()

    headers = {"Authorization": f"Bearer {token}"}

    # Pagina 1: 2 de 6.
    r = await client.get(
        "/api/v1/transacoes/alertas?limite=2",
        headers=headers,
    )
    assert r.status_code == 200, r.json()
    p1 = r.json()

    assert len(p1["itens"]) == 2
    assert p1["has_more"] is True
    assert p1["next_cursor"] is not None

    # Pagina 2: mais 2, sem repetir a pagina 1.
    r = await client.get(
        f"/api/v1/transacoes/alertas?limite=2&cursor={p1['next_cursor']}",
        headers=headers,
    )
    assert r.status_code == 200, r.json()
    p2 = r.json()

    assert len(p2["itens"]) == 2
    assert p2["has_more"] is True
    assert p2["next_cursor"] is not None

    ids_p1 = {i["id"] for i in p1["itens"]}
    ids_p2 = {i["id"] for i in p2["itens"]}
    assert ids_p1.isdisjoint(ids_p2)

    # Pagina 3: últimos 2 alertas.
    r = await client.get(
        f"/api/v1/transacoes/alertas?limite=2&cursor={p2['next_cursor']}",
        headers=headers,
    )
    assert r.status_code == 200, r.json()
    p3 = r.json()

    assert len(p3["itens"]) == 2
    assert p3["has_more"] is False
    assert p3["next_cursor"] is None

    ids_p3 = {i["id"] for i in p3["itens"]}
    assert ids_p1.isdisjoint(ids_p3)
    assert ids_p2.isdisjoint(ids_p3)


async def test_alertas_cursor_malformado_400(client):
    token = await _registrar(
        client,
        email="cur_alertas2@x.com",
        cpf="404.404.404-08",
    )

    r = await client.get(
        "/api/v1/transacoes/alertas?cursor=nao-e-base64-valido!!",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


async def test_alertas_filtro_tipo(client):
    token = await _registrar(client, email="al4@x.com", cpf="444.444.440-10")
    await _criar_alerta_60(client, token)

    r = await client.get(
        "/api/v1/transacoes/alertas?tipo=faturamento_faixa",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert len(r.json()["itens"]) >= 1

    r = await client.get(
        "/api/v1/transacoes/alertas?tipo=inexistente",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["itens"] == []


# ============================================================
# POST /alertas/{id}/lido
# ============================================================

async def test_marcar_lido_idempotente(client):
    token = await _registrar(client, email="al5@x.com", cpf="555.555.550-40")
    await _criar_alerta_60(client, token)

    async with conexao() as conn:
        aid = await conn.fetchval(
            "SELECT id FROM alerts WHERE tipo = 'faturamento_faixa' LIMIT 1"
        )

    r1 = await client.post(
        f"/api/v1/transacoes/alertas/{aid}/lido",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200
    assert r1.json()["marcado_agora"] is True

    r2 = await client.post(
        f"/api/v1/transacoes/alertas/{aid}/lido",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["marcado_agora"] is False


async def test_marcar_lido_404_inexistente(client):
    token = await _registrar(client, email="al6@x.com", cpf="666.666.660-70")
    r = await client.post(
        "/api/v1/transacoes/alertas/00000000-0000-0000-0000-000000000000/lido",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


async def test_marcar_lido_400_id_invalido(client):
    token = await _registrar(client, email="al7@x.com", cpf="777.777.770-09")
    r = await client.post(
        "/api/v1/transacoes/alertas/nao-uuid/lido",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


async def test_marcar_lido_isolamento_por_usuario(client):
    token_a = await _registrar(client, email="ala@x.com", cpf="888.888.880-20")
    token_b = await _registrar(client, email="alb@x.com", cpf="999.999.990-50")

    await _criar_alerta_60(client, token_a)
    async with conexao() as conn:
        aid = await conn.fetchval(
            "SELECT id FROM alerts WHERE tipo = 'faturamento_faixa' LIMIT 1"
        )

    r = await client.post(
        f"/api/v1/transacoes/alertas/{aid}/lido",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404


async def test_alertas_sem_jwt_401(client):
    r = await client.get("/api/v1/transacoes/alertas")
    assert r.status_code == 401


# ============================================================
# /fila com cursor
# ============================================================

async def test_fila_cursor_e_has_more(client):
    token = await _registrar(client, email="cur@x.com", cpf="101.101.102-69")

    # Cola 5 entradas genericas -> 5 na fila
    texto = (
        "25/09 PIX RECEBIDO JOAO R$ 10,00\n"
        "24/09 PIX RECEBIDO MARIA R$ 20,00\n"
        "23/09 DEPOSITO EM CONTA R$ 30,00\n"
        "22/09 CREDITO EM CONTA R$ 40,00\n"
        "21/09 TRANSFERENCIA RECEBIDA R$ 50,00"
    )
    r = await _colar(client, token, texto)
    assert r.status_code == 201

    # Pagina 1: limite 2
    r = await client.get(
        "/api/v1/transacoes/fila?limite=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    p1 = r.json()
    assert len(p1["itens"]) == 2
    assert p1["has_more"] is True
    assert p1["next_cursor"] is not None

    # Pagina 2
    r = await client.get(
        f"/api/v1/transacoes/fila?limite=2&cursor={p1['next_cursor']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    p2 = r.json()
    assert len(p2["itens"]) == 2
    ids_p1 = {i["id"] for i in p1["itens"]}
    ids_p2 = {i["id"] for i in p2["itens"]}
    assert ids_p1.isdisjoint(ids_p2)

    # Pagina 3
    r = await client.get(
        f"/api/v1/transacoes/fila?limite=2&cursor={p2['next_cursor']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    p3 = r.json()
    assert len(p3["itens"]) == 1
    assert p3["has_more"] is False
    assert p3["next_cursor"] is None


async def test_fila_cursor_malformado_400(client):
    token = await _registrar(client, email="cur2@x.com", cpf="202.202.202-55")
    r = await client.get(
        "/api/v1/transacoes/fila?cursor=nao-e-base64-valido!!",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400

