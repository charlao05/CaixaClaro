import uuid

import pytest
from fastapi import HTTPException

from caixaclaro.services import contas


@pytest.mark.asyncio
async def test_processar_item_created_rejeita_payload_incompleto():
    class Conn:
        pass

    with pytest.raises(HTTPException) as exc:
        await contas.processar_item_created(Conn(), {})

    assert exc.value.status_code == 400
    assert exc.value.detail["erro"] == "WEBHOOK_PAYLOAD_INVALIDO"


@pytest.mark.asyncio
async def test_processar_item_created_rejeita_client_user_id_invalido():
    class Conn:
        pass

    with pytest.raises(HTTPException) as exc:
        await contas.processar_item_created(
            Conn(),
            {"itemId": "item-123", "clientUserId": "nao-e-uuid"},
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["erro"] == "WEBHOOK_CLIENTUSERID_INVALIDO"


@pytest.mark.asyncio
async def test_processar_item_created_busca_item_e_accounts(monkeypatch):
    user_id = uuid.uuid4()
    chamadas = []

    async def buscar_item(item_id):
        chamadas.append(("item", item_id))
        return {"id": item_id}

    async def listar_accounts(item_id):
        chamadas.append(("accounts", item_id))
        return []

    monkeypatch.setattr(contas.pluggy, "buscar_item", buscar_item)
    monkeypatch.setattr(contas.pluggy, "listar_accounts", listar_accounts)

    class Conn:
        pass

    conn = Conn()

    with pytest.raises(AttributeError):
        await contas.processar_item_created(
            conn,
            {"itemId": "item-123", "clientUserId": str(user_id)},
        )

    assert chamadas == [
        ("item", "item-123"),
        ("accounts", "item-123"),
    ]


async def test_get_contas_vazio(client):
    """Usuario sem contas: resposta vazia."""
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "sem-contas@x.com", "senha": "senha123", "cpf": "555.555.555-55"},
    )
    assert r.status_code == 201
    token = r.json()["token"]

    r = await client.get(
        "/api/v1/contas",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    assert r.json() == {"itens": []}


async def test_get_contas_lista_ordenado(client, monkeypatch):
    """Apos item/created, GET /contas retorna as contas criadas."""
    from caixaclaro.db import conexao
    from caixaclaro.services import pluggy as pluggy_mod

    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "com-contas@x.com", "senha": "senha123", "cpf": "666.666.666-66"},
    )
    assert r.status_code == 201
    token = r.json()["token"]
    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", "com-contas@x.com"
        )

    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return [
            {"id": "acc-1", "name": "Conta Corrente"},
            {"id": "acc-2", "name": "Poupanca"},
        ]

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)

    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": "evt-contas-1",
            "itemId": "item-abc",
            "clientUserId": str(user_id),
        },
    )
    assert r.status_code == 200, r.json()

    r = await client.get(
        "/api/v1/contas",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    assert len(body["itens"]) == 2

    nomes = {i["nome"] for i in body["itens"]}
    assert nomes == {"Conta Corrente", "Poupanca"}

    for item in body["itens"]:
        assert item["provider"] == "pluggy"
        assert item["provider_account_id"] in {"acc-1", "acc-2"}
        assert "id" in item and "criado_em" in item


async def test_get_contas_isolamento_por_usuario(client, monkeypatch):
    """Usuario A nao ve contas de usuario B."""
    from caixaclaro.db import conexao
    from caixaclaro.services import pluggy as pluggy_mod

    # Usuario A com conta
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "a-contas@x.com", "senha": "senha123", "cpf": "777.777.777-77"},
    )
    token_a = r.json()["token"]
    async with conexao() as conn:
        uid_a = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", "a-contas@x.com"
        )

    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return [{"id": "acc-a", "name": "Conta A"}]

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)

    await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": "evt-isolamento-a",
            "itemId": "item-a",
            "clientUserId": str(uid_a),
        },
    )

    # Usuario B sem conta
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "b-contas@x.com", "senha": "senha123", "cpf": "888.888.888-88"},
    )
    token_b = r.json()["token"]

    r = await client.get(
        "/api/v1/contas",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 200
    assert r.json() == {"itens": []}

    # E A continua vendo sua propria conta
    r = await client.get(
        "/api/v1/contas",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 200
    assert len(r.json()["itens"]) == 1
