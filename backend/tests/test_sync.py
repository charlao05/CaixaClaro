"""Testes HTTP de sync — POST /contas/{id}/sync e GET /sync/{sync_id}."""
import uuid

from caixaclaro.db import conexao
from caixaclaro.services import pluggy as pluggy_mod


async def _registrar(client, email, cpf):
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


def _mockar_pluggy(monkeypatch, accounts):
    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return accounts

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)


async def _criar_conta(client, monkeypatch, email, cpf, acc_id, item_id):
    token, user_id = await _registrar(client, email, cpf)
    _mockar_pluggy(monkeypatch, [{"id": acc_id, "name": "Conta"}])
    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": f"evt-{item_id}",
            "itemId": item_id,
            "clientUserId": user_id,
        },
    )
    assert r.status_code == 200, r.json()
    async with conexao() as conn:
        account_id = await conn.fetchval(
            "SELECT id FROM accounts WHERE user_id = $1 AND provider_account_id = $2",
            uuid.UUID(user_id),
            acc_id,
        )
    return token, user_id, str(account_id)


async def test_iniciar_sync_cria_pendente(client, monkeypatch):
    token, user_id, account_id = await _criar_conta(
        client, monkeypatch, "sync1@x.com", "111.111.111-11", "acc-s1", "item-s1"
    )
    async with conexao() as conn:
        await conn.execute(
            "DELETE FROM sync_requests WHERE user_id = $1",
            uuid.UUID(user_id),
        )

    r = await client.post(
        f"/api/v1/contas/{account_id}/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 202, r.json()
    body = r.json()
    assert body["status"] == "pendente"
    assert "sync_id" in body


async def test_iniciar_sync_reusa_pendente_existente(client, monkeypatch):
    token, _, account_id = await _criar_conta(
        client, monkeypatch, "sync2@x.com", "222.222.222-22", "acc-s2", "item-s2"
    )
    headers = {"Authorization": f"Bearer {token}"}
    r1 = await client.post(f"/api/v1/contas/{account_id}/sync", headers=headers)
    r2 = await client.post(f"/api/v1/contas/{account_id}/sync", headers=headers)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["sync_id"] == r2.json()["sync_id"]


async def test_consultar_sync_200(client, monkeypatch):
    token, _, account_id = await _criar_conta(
        client, monkeypatch, "sync3@x.com", "333.333.333-33", "acc-s3", "item-s3"
    )
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post(f"/api/v1/contas/{account_id}/sync", headers=headers)
    sync_id = r.json()["sync_id"]

    r = await client.get(f"/api/v1/sync/{sync_id}", headers=headers)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["sync_id"] == sync_id
    assert body["status"] == "pendente"
    assert body["erro"] is None
    assert "criado_em" in body


async def test_consultar_sync_inexistente_404(client, monkeypatch):
    token, _, _ = await _criar_conta(
        client, monkeypatch, "sync4@x.com", "444.444.444-44", "acc-s4", "item-s4"
    )
    r = await client.get(
        f"/api/v1/sync/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert r.json()["erro"] == "SYNC_NAO_ENCONTRADO"


async def test_consultar_sync_de_outro_usuario_404(client, monkeypatch):
    token_a, _, account_a = await _criar_conta(
        client, monkeypatch, "sync5a@x.com", "555.555.555-55", "acc-s5", "item-s5"
    )
    r = await client.post(
        f"/api/v1/contas/{account_a}/sync",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    sync_id = r.json()["sync_id"]

    token_b, _, _ = await _criar_conta(
        client, monkeypatch, "sync5b@x.com", "556.556.556-56", "acc-s5b", "item-s5b"
    )
    r = await client.get(
        f"/api/v1/sync/{sync_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404


async def test_iniciar_sync_conta_inexistente_404(client, monkeypatch):
    token, _, _ = await _criar_conta(
        client, monkeypatch, "sync6@x.com", "666.666.666-66", "acc-s6", "item-s6"
    )
    r = await client.post(
        f"/api/v1/contas/{uuid.uuid4()}/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert r.json()["erro"] == "CONTA_NAO_ENCONTRADA"


async def test_iniciar_sync_conta_de_outro_usuario_404(client, monkeypatch):
    _, _, account_a = await _criar_conta(
        client, monkeypatch, "sync7a@x.com", "777.777.777-77", "acc-s7", "item-s7"
    )
    token_b, _, _ = await _criar_conta(
        client, monkeypatch, "sync7b@x.com", "778.778.778-78", "acc-s7b", "item-s7b"
    )
    r = await client.post(
        f"/api/v1/contas/{account_a}/sync",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
