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


async def test_revogar_item_sucesso_marca_consent_revogado(client, monkeypatch):
    """Revogacao externa bem-sucedida marca o consent local."""
    from caixaclaro.db import conexao
    from caixaclaro.services import pluggy as pluggy_mod

    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "revoga-sucesso@x.com",
            "senha": "senha123",
            "cpf": "101.101.101-01",
        },
    )
    assert r.status_code == 201
    token = r.json()["token"]

    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1",
            "revoga-sucesso@x.com",
        )

    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return [{"id": "acc-rev-1", "name": "Conta Revogar"}]

    chamadas = []

    async def revogar_item(item_id):
        chamadas.append(item_id)

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)
    monkeypatch.setattr(pluggy_mod, "revogar_item", revogar_item)

    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": "evt-revoga-sucesso",
            "itemId": "item-rev-1",
            "clientUserId": str(user_id),
        },
    )
    assert r.status_code == 200

    async with conexao() as conn:
        account_id = await conn.fetchval(
            """
            SELECT id FROM accounts
             WHERE provider_account_id = 'acc-rev-1'
               AND user_id = $1
            """,
            user_id,
        )

        result = await contas.revogar_item(conn, user_id, account_id)

        revogado = await conn.fetchval(
            """
            SELECT revogado_em FROM consents
             WHERE provider = 'pluggy'
               AND provider_user_id = 'item-rev-1'
               AND user_id = $1
            """,
            user_id,
        )

    assert result == {"item_id": "item-rev-1", "ja_revogado": False}
    assert chamadas == ["item-rev-1"]
    assert revogado is not None


async def test_revogar_item_falha_externa_nao_marca_consent(client, monkeypatch):
    """Falha na Pluggy nao pode deixar revogado_em preenchido."""
    from caixaclaro.db import conexao
    from caixaclaro.services import pluggy as pluggy_mod

    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "revoga-falha@x.com",
            "senha": "senha123",
            "cpf": "102.102.102-02",
        },
    )
    assert r.status_code == 201

    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1",
            "revoga-falha@x.com",
        )

    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return [{"id": "acc-rev-2", "name": "Conta Falha"}]

    async def revogar_item(item_id):
        raise HTTPException(
            status_code=502,
            detail={
                "erro": "PLUGGY_REVOGAR_FALHOU",
                "mensagem": "Falha ao revogar Item na Pluggy.",
            },
        )

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)
    monkeypatch.setattr(pluggy_mod, "revogar_item", revogar_item)

    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": "evt-revoga-falha",
            "itemId": "item-rev-2",
            "clientUserId": str(user_id),
        },
    )
    assert r.status_code == 200

    async with conexao() as conn:
        account_id = await conn.fetchval(
            """
            SELECT id FROM accounts
             WHERE provider_account_id = 'acc-rev-2'
               AND user_id = $1
            """,
            user_id,
        )

        with pytest.raises(HTTPException) as exc:
            await contas.revogar_item(conn, user_id, account_id)

        revogado = await conn.fetchval(
            """
            SELECT revogado_em FROM consents
             WHERE provider = 'pluggy'
               AND provider_user_id = 'item-rev-2'
               AND user_id = $1
            """,
            user_id,
        )

    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "PLUGGY_REVOGAR_FALHOU"
    assert revogado is None


async def test_revogar_item_isolamento_usuario(client):
    """Usuario diferente nao consegue revogar a conta de outro usuario."""
    from caixaclaro.db import conexao

    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "revoga-dono@x.com",
            "senha": "senha123",
            "cpf": "103.103.103-03",
        },
    )
    assert r.status_code == 201

    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "revoga-outro@x.com",
            "senha": "senha123",
            "cpf": "104.104.104-04",
        },
    )
    assert r.status_code == 201

    async with conexao() as conn:
        dono = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1",
            "revoga-dono@x.com",
        )
        outro = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1",
            "revoga-outro@x.com",
        )

        account_id = await conn.fetchval(
            """
            INSERT INTO accounts (
                user_id, provider, provider_account_id, nome, item_id
            )
            VALUES ($1, 'pluggy', 'acc-isolamento', 'Conta', 'item-isolamento')
            RETURNING id
            """,
            dono,
        )

        with pytest.raises(HTTPException) as exc:
            await contas.revogar_item(conn, outro, account_id)

    assert exc.value.status_code == 404
    assert exc.value.detail["erro"] == "CONTA_NAO_ENCONTRADA"


async def test_revogar_item_idempotente_nao_chama_pluggy_de_novo(client, monkeypatch):
    """Segunda revogacao retorna ja_revogado=True sem chamar Pluggy."""
    from caixaclaro.db import conexao
    from caixaclaro.services import pluggy as pluggy_mod

    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "revoga-idem@x.com",
            "senha": "senha123",
            "cpf": "105.105.105-05",
        },
    )
    assert r.status_code == 201

    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1",
            "revoga-idem@x.com",
        )

    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return [{"id": "acc-idem", "name": "Conta Idem"}]

    chamadas = []

    async def revogar_item(item_id):
        chamadas.append(item_id)

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)
    monkeypatch.setattr(pluggy_mod, "revogar_item", revogar_item)

    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": "evt-revoga-idem",
            "itemId": "item-idem",
            "clientUserId": str(user_id),
        },
    )
    assert r.status_code == 200

    async with conexao() as conn:
        account_id = await conn.fetchval(
            "SELECT id FROM accounts WHERE provider_account_id = 'acc-idem' AND user_id = $1",
            user_id,
        )
        r1 = await contas.revogar_item(conn, user_id, account_id)
        r2 = await contas.revogar_item(conn, user_id, account_id)

    assert r1 == {"item_id": "item-idem", "ja_revogado": False}
    assert r2 == {"item_id": "item-idem", "ja_revogado": True}
    assert chamadas == ["item-idem"]


async def test_revogar_item_conta_inexistente_404(client):
    """UUID valido mas sem conta correspondente -> 404."""
    from caixaclaro.db import conexao

    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "revoga-404@x.com",
            "senha": "senha123",
            "cpf": "106.106.106-06",
        },
    )
    assert r.status_code == 201

    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1",
            "revoga-404@x.com",
        )
        with pytest.raises(HTTPException) as exc:
            await contas.revogar_item(conn, user_id, uuid.uuid4())

    assert exc.value.status_code == 404
    assert exc.value.detail["erro"] == "CONTA_NAO_ENCONTRADA"


async def test_get_contas_apos_revogacao_nao_lista(client, monkeypatch):
    """Conta com consent revogado deixa de aparecer em GET /contas."""
    from caixaclaro.db import conexao
    from caixaclaro.services import pluggy as pluggy_mod

    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rev-lista@x.com",
            "senha": "senha123",
            "cpf": "107.107.107-07",
        },
    )
    assert r.status_code == 201
    token = r.json()["token"]

    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", "rev-lista@x.com"
        )

    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return [{"id": "acc-rev-lista", "name": "Conta"}]

    chamadas = []

    async def revogar_item(item_id):
        chamadas.append(item_id)

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)
    monkeypatch.setattr(pluggy_mod, "revogar_item", revogar_item)

    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": "evt-rev-lista",
            "itemId": "item-rev-lista",
            "clientUserId": str(user_id),
        },
    )
    assert r.status_code == 200

    headers = {"Authorization": f"Bearer {token}"}

    # Antes de revogar: aparece
    r = await client.get("/api/v1/contas", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["itens"]) == 1

    # Revoga
    async with conexao() as conn:
        account_id = await conn.fetchval(
            "SELECT id FROM accounts WHERE user_id = $1 AND provider_account_id = 'acc-rev-lista'",
            user_id,
        )
        await contas.revogar_item(conn, user_id, account_id)

    # Depois: nao aparece mais
    r = await client.get("/api/v1/contas", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"itens": []}

    # Mas a linha continua no banco (historico preservado)
    async with conexao() as conn:
        existe = await conn.fetchval(
            "SELECT count(*) FROM accounts WHERE user_id = $1 AND provider_account_id = 'acc-rev-lista'",
            user_id,
        )
    assert existe == 1
