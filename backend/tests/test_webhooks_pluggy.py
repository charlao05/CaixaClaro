"""Integracao POST /webhooks/pluggy (M3b)."""
from caixaclaro.db import conexao
from caixaclaro.services import pluggy as pluggy_mod


async def _registrar(client, email="wh@x.com", cpf="333.333.333-33"):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    token = r.json()["token"]
    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
    return token, str(user_id)


def _mockar_pluggy(monkeypatch, accounts=None):
    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return accounts if accounts is not None else []

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)


async def _contar(tabela):
    async with conexao() as conn:
        return await conn.fetchval(f"SELECT count(*) FROM {tabela}")


async def test_webhook_item_created_cria_consent_account_e_sync(client, monkeypatch):
    _, user_id = await _registrar(client)
    _mockar_pluggy(
        monkeypatch,
        accounts=[
            {"id": "acc-1", "name": "Conta Principal"},
            {"id": "acc-2", "name": "Conta Secundaria"},
        ],
    )

    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": "evt-1",
            "itemId": "item-123",
            "clientUserId": user_id,
        },
    )

    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["ok"] is True
    assert body["processado"]["item_id"] == "item-123"
    assert body["processado"]["accounts"] == 2
    assert body["processado"]["sync_requests"] == 2

    assert await _contar("consents") == 1
    assert await _contar("accounts") == 2
    assert await _contar("sync_requests") == 2
    assert await _contar("webhook_events") == 1

    async with conexao() as conn:
        item_ids = await conn.fetch(
            """
            SELECT item_id
              FROM accounts
             WHERE user_id = $1
             ORDER BY provider_account_id
            """,
            user_id,
        )
    assert [r["item_id"] for r in item_ids] == ["item-123", "item-123"]


async def test_webhook_mesmo_event_id_nao_duplica(client, monkeypatch):
    _, user_id = await _registrar(client)
    _mockar_pluggy(monkeypatch, accounts=[{"id": "acc-1", "name": "Conta"}])

    payload = {
        "event": "item/created",
        "eventId": "evt-repetido",
        "itemId": "item-999",
        "clientUserId": user_id,
    }
    r1 = await client.post("/api/v1/webhooks/pluggy", json=payload)
    r2 = await client.post("/api/v1/webhooks/pluggy", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json() == {"ok": True, "duplicado": True}

    assert await _contar("consents") == 1
    assert await _contar("accounts") == 1
    assert await _contar("sync_requests") == 1
    assert await _contar("webhook_events") == 1


async def test_webhook_payload_invalido_nao_registra_evento(client):
    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={"event": "item/created"},
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "WEBHOOK_PAYLOAD_INVALIDO"
    assert await _contar("webhook_events") == 0


async def test_webhook_evento_desconhecido_apenas_registra(client):
    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "transactions/created",
            "eventId": "evt-tx",
            "itemId": "item-x",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "ignorado": "transactions/created"}
    assert await _contar("webhook_events") == 1
    assert await _contar("consents") == 0

