"""Testes de API — movimentação de estoque (M11).

Cobre idempotência (Idempotency-Key), o guardrail de estoque nunca
negativo via HTTP (409), e isolamento por usuário.
"""
import uuid
from decimal import Decimal

from tests._cpf import cpf_valido


async def _registrar(client, email_prefix: str) -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{email_prefix}@x.com",
            "senha": "senha123",
            "cpf": cpf_valido(str(uuid.uuid4().int)[:9]),
        },
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


async def _criar_produto(client, headers, nome="Produto Teste"):
    r = await client.post(
        "/api/v1/produtos",
        json={"tipo": "produto", "nome": nome, "controla_estoque": True},
        headers=headers,
    )
    assert r.status_code == 201, r.json()
    return r.json()["id"]


async def test_entrada_aumenta_saldo(client):
    token = await _registrar(client, "est-entrada")
    headers = {"Authorization": f"Bearer {token}"}
    produto_id = await _criar_produto(client, headers)

    r = await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "entrada_compra", "quantidade": "10"},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.json()

    r = await client.get(f"/api/v1/produtos/{produto_id}/saldo", headers=headers)
    assert Decimal(r.json()["saldo"]) == Decimal(10)


async def test_saida_diminui_saldo(client):
    token = await _registrar(client, "est-saida")
    headers = {"Authorization": f"Bearer {token}"}
    produto_id = await _criar_produto(client, headers)

    await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "entrada_compra", "quantidade": "10"},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    r = await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "saida_venda", "quantidade": "4"},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.json()

    r = await client.get(f"/api/v1/produtos/{produto_id}/saldo", headers=headers)
    assert Decimal(r.json()["saldo"]) == Decimal(6)


async def test_estoque_negativo_recusado_409(client):
    """NUNCA permitir estoque negativo — guardrail via HTTP real."""
    token = await _registrar(client, "est-negativo")
    headers = {"Authorization": f"Bearer {token}"}
    produto_id = await _criar_produto(client, headers)

    r = await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "saida_venda", "quantidade": "1"},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 409, r.json()
    assert r.json()["erro"] == "ESTOQUE_NEGATIVO_RECUSADO"

    r = await client.get(f"/api/v1/produtos/{produto_id}/saldo", headers=headers)
    assert Decimal(r.json()["saldo"]) == Decimal(0)


async def test_idempotencia_mesma_chave_nao_duplica_movimento(client):
    token = await _registrar(client, "est-idem")
    headers = {"Authorization": f"Bearer {token}"}
    produto_id = await _criar_produto(client, headers)
    chave = str(uuid.uuid4())

    r1 = await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "entrada_compra", "quantidade": "5"},
        headers={**headers, "Idempotency-Key": chave},
    )
    r2 = await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "entrada_compra", "quantidade": "5"},
        headers={**headers, "Idempotency-Key": chave},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    r = await client.get(f"/api/v1/produtos/{produto_id}/saldo", headers=headers)
    assert Decimal(r.json()["saldo"]) == Decimal(5)


async def test_movimento_sem_idempotency_key_422(client):
    token = await _registrar(client, "est-sem-chave")
    headers = {"Authorization": f"Bearer {token}"}
    produto_id = await _criar_produto(client, headers)

    r = await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "entrada_compra", "quantidade": "5"},
        headers=headers,
    )
    assert r.status_code == 422


async def test_tipo_movimento_invalido_422(client):
    token = await _registrar(client, "est-tipo-invalido")
    headers = {"Authorization": f"Bearer {token}"}
    produto_id = await _criar_produto(client, headers)

    r = await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "tipo_que_nao_existe", "quantidade": "1"},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 422
    assert r.json()["erro"] == "TIPO_MOVIMENTO_INVALIDO"


async def test_listar_movimentos_isolamento_por_usuario(client):
    token_a = await _registrar(client, "est-iso-a")
    token_b = await _registrar(client, "est-iso-b")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    produto_id = await _criar_produto(client, headers_a)
    await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "entrada_compra", "quantidade": "3"},
        headers={**headers_a, "Idempotency-Key": str(uuid.uuid4())},
    )

    r = await client.get(f"/api/v1/produtos/{produto_id}/movimentos", headers=headers_b)
    assert r.status_code == 404


async def test_quantidade_zero_rejeitada(client):
    token = await _registrar(client, "est-qtd-zero")
    headers = {"Authorization": f"Bearer {token}"}
    produto_id = await _criar_produto(client, headers)

    r = await client.post(
        f"/api/v1/produtos/{produto_id}/movimentos",
        json={"tipo_movimento": "entrada_compra", "quantidade": "0"},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 422