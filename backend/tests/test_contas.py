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
