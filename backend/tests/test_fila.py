"""Fila de revisao — M5A.

Leitura de transacoes com needs_review=true, ordenadas por criado_em DESC.
"""
import uuid

from caixaclaro.db import conexao


async def _registrar(client, email="fila@x.com", cpf="222.222.222-22"):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


def _key():
    return str(uuid.uuid4())


async def _colar(client, token, texto, *, key=None):
    return await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": key or _key(),
        },
        json={"texto": texto},
    )


async def test_fila_vazia_retorna_itens_vazio(client):
    token = await _registrar(client)
    r = await client.get(
        "/api/v1/transacoes/fila",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    assert r.json()["itens"] == []


async def test_fila_traz_somente_needs_review(client):
    token = await _registrar(client)
    # "PIX RECEBIDO JOAO" cai em outros -> needs_review=true
    # "PAGTO GUIA DAS SIMPLES" vira imposto_das -> needs_review=false
    texto = (
        "25/09 PIX RECEBIDO JOAO R$ 100,00\n"
        "24/09 PAGTO GUIA DAS SIMPLES R$ 50,00"
    )
    r = await _colar(client, token, texto)
    assert r.status_code == 201

    r = await client.get(
        "/api/v1/transacoes/fila",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    itens = r.json()["itens"]
    assert len(itens) == 1
    assert itens[0]["categoria"] == "outros"
    assert itens[0]["needs_review"] is True


async def test_fila_ordena_criado_em_desc(client):
    token = await _registrar(client)
    texto = (
        "20/09 PIX RECEBIDO ANA R$ 10,00\n"
        "25/09 PIX RECEBIDO BIA R$ 20,00\n"
        "22/09 PIX RECEBIDO CARLA R$ 30,00"
    )
    r = await _colar(client, token, texto)
    assert r.status_code == 201

    r = await client.get(
        "/api/v1/transacoes/fila",
        headers={"Authorization": f"Bearer {token}"},
    )
    itens = r.json()["itens"]
    # Contrato §CONTRATOS_INTERNOS linha 286: /fila ordena por
    # criado_em DESC, id DESC. Como as 3 linhas entram no mesmo
    # loop de INSERT, criado_em segue a ordem de insercao e nao
    # a ordem de `data`.
    criados = [i["criado_em"] for i in itens]
    assert criados == sorted(criados, reverse=True)


async def test_fila_isolamento_por_usuario(client):
    token_a = await _registrar(client, email="a@x.com", cpf="111.111.111-11")
    token_b = await _registrar(client, email="b@x.com", cpf="333.333.333-33")

    await _colar(client, token_a, "25/09 PIX RECEBIDO JOAO R$ 100,00")

    r = await client.get(
        "/api/v1/transacoes/fila",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 200
    assert r.json()["itens"] == []


async def test_fila_sem_jwt_401(client):
    r = await client.get("/api/v1/transacoes/fila")
    assert r.status_code == 401


async def test_fila_limite_fora_da_faixa_422(client):
    token = await _registrar(client)
    r = await client.get(
        "/api/v1/transacoes/fila?limite=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422
