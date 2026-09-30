"""Testes do client Pluggy — M3b (connect token).

Cobrem:
  - fluxo feliz: /auth -> /connect_token com clientUserId = user_id
  - sem credenciais -> 503 PLUGGY_NAO_CONFIGURADO
  - /auth falha -> 502 PLUGGY_AUTH_FALHOU
  - /connect_token falha -> 502 PLUGGY_CONNECT_TOKEN_FALHOU

Sem I/O real: httpx.AsyncClient e substituido por MockTransport.
"""
import json

import httpx
import pytest
from fastapi import HTTPException

from caixaclaro.config import settings
from caixaclaro.services import pluggy as pluggy_mod


def _com_credenciais(monkeypatch):
    s = settings()
    monkeypatch.setattr(s, "pluggy_client_id", "client-id")
    monkeypatch.setattr(s, "pluggy_client_secret", "client-secret")
    monkeypatch.setattr(s, "pluggy_base_url", "https://api.pluggy.ai")


def _sem_credenciais(monkeypatch):
    s = settings()
    monkeypatch.setattr(s, "pluggy_client_id", None)
    monkeypatch.setattr(s, "pluggy_client_secret", None)
    monkeypatch.setattr(s, "pluggy_base_url", "https://api.pluggy.ai")


def _mock_transport(handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    return factory


async def test_criar_connect_token_envia_client_user_id(monkeypatch):
    _com_credenciais(monkeypatch)
    chamadas = []

    async def handler(request):
        chamadas.append(request.url.path)
        body = json.loads(request.content)

        if request.url.path == "/auth":
            assert request.method == "POST"
            assert body == {
                "clientId": "client-id",
                "clientSecret": "client-secret",
            }
            return httpx.Response(200, json={"apiKey": "api-key"})

        if request.url.path == "/connect_token":
            assert request.method == "POST"
            assert request.headers["X-API-KEY"] == "api-key"
            assert body == {"options": {"clientUserId": "123"}}
            return httpx.Response(
                201,
                json={
                    "accessToken": "token-abc",
                    "expiresAt": "2026-09-27T12:00:00Z",
                },
            )

        return httpx.Response(404)

    monkeypatch.setattr(pluggy_mod.httpx, "AsyncClient", _mock_transport(handler))

    out = await pluggy_mod.criar_connect_token("123")

    assert out == {
        "connect_token": "token-abc",
        "expira_em": "2026-09-27T12:00:00Z",
    }
    assert chamadas == ["/auth", "/connect_token"]


async def test_sem_credenciais_erro_503(monkeypatch):
    _sem_credenciais(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await pluggy_mod.criar_connect_token("123")
    assert exc.value.status_code == 503
    assert exc.value.detail["erro"] == "PLUGGY_NAO_CONFIGURADO"


async def test_auth_falha_erro_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        return httpx.Response(401)

    monkeypatch.setattr(pluggy_mod.httpx, "AsyncClient", _mock_transport(handler))

    with pytest.raises(HTTPException) as exc:
        await pluggy_mod.criar_connect_token("123")
    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "PLUGGY_AUTH_FALHOU"


async def test_connect_token_falha_erro_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        return httpx.Response(500)

    monkeypatch.setattr(pluggy_mod.httpx, "AsyncClient", _mock_transport(handler))

    with pytest.raises(HTTPException) as exc:
        await pluggy_mod.criar_connect_token("123")
    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "PLUGGY_CONNECT_TOKEN_FALHOU"



async def test_buscar_item(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        if request.url.path == "/items/item-123":
            assert request.method == "GET"
            assert request.headers["X-API-KEY"] == "api-key"
            return httpx.Response(
                200,
                json={"id": "item-123", "status": "UPDATED"},
            )
        return httpx.Response(404)

    monkeypatch.setattr(
        pluggy_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    out = await pluggy_mod.buscar_item("item-123")

    assert out == {"id": "item-123", "status": "UPDATED"}


async def test_buscar_item_falha_erro_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        return httpx.Response(404)

    monkeypatch.setattr(
        pluggy_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    with pytest.raises(HTTPException) as exc:
        await pluggy_mod.buscar_item("item-123")

    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "PLUGGY_ITEM_FALHOU"


async def test_listar_accounts(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        if request.url.path == "/accounts":
            assert request.method == "GET"
            assert request.headers["X-API-KEY"] == "api-key"
            assert request.url.params["itemId"] == "item-123"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": "acc-1", "name": "Conta Principal"},
                        {"id": "acc-2", "name": "Conta Secundaria"},
                    ]
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(
        pluggy_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    out = await pluggy_mod.listar_accounts("item-123")

    assert out == [
        {"id": "acc-1", "name": "Conta Principal"},
        {"id": "acc-2", "name": "Conta Secundaria"},
    ]


async def test_listar_accounts_falha_erro_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        return httpx.Response(500)

    monkeypatch.setattr(
        pluggy_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    with pytest.raises(HTTPException) as exc:
        await pluggy_mod.listar_accounts("item-123")

    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "PLUGGY_ACCOUNTS_FALHOU"

async def test_revogar_item(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        if request.url.path == "/items/item-123":
            assert request.method == "DELETE"
            assert request.headers["X-API-KEY"] == "api-key"
            return httpx.Response(200, json={"id": "item-123"})
        return httpx.Response(404)

    monkeypatch.setattr(
        pluggy_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    await pluggy_mod.revogar_item("item-123")


async def test_revogar_item_falha_erro_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        return httpx.Response(500)

    monkeypatch.setattr(
        pluggy_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    with pytest.raises(HTTPException) as exc:
        await pluggy_mod.revogar_item("item-123")

    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "PLUGGY_REVOGAR_FALHOU"


async def test_revogar_item_404_e_sucesso(monkeypatch):
    """404 e sucesso: item ja nao existe, estado desejado satisfeito."""
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        return httpx.Response(404)

    monkeypatch.setattr(
        pluggy_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    await pluggy_mod.revogar_item("item-inexistente")


async def test_listar_transactions(monkeypatch):
    _com_credenciais(monkeypatch)

    chamadas = []

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        if request.url.path == "/v2/transactions":
            assert request.method == "GET"
            assert request.headers["X-API-KEY"] == "api-key"
            assert request.url.params["accountId"] == "acc-1"
            after = request.url.params.get("after")
            chamadas.append(after)
            if after is None:
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {"id": "tx-1", "date": "2026-09-01", "amount": 100.5},
                            {"id": "tx-2", "date": "2026-09-02", "amount": -50.0},
                        ],
                        "next": "cursor-2",
                    },
                )
            assert after == "cursor-2"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": "tx-3", "date": "2026-09-03", "amount": 25.0},
                    ],
                    "next": None,
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(
        pluggy_mod.httpx, "AsyncClient", _mock_transport(handler)
    )

    out1 = await pluggy_mod.listar_transactions("acc-1")
    assert out1["next"] == "cursor-2"
    assert len(out1["results"]) == 2
    assert out1["results"][0]["id"] == "tx-1"

    out2 = await pluggy_mod.listar_transactions("acc-1", cursor=out1["next"])
    assert out2["next"] is None
    assert len(out2["results"]) == 1
    assert out2["results"][0]["id"] == "tx-3"

    assert chamadas == [None, "cursor-2"]


async def test_listar_transactions_falha_erro_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "api-key"})
        return httpx.Response(500)

    monkeypatch.setattr(
        pluggy_mod.httpx, "AsyncClient", _mock_transport(handler)
    )

    with pytest.raises(HTTPException) as exc:
        await pluggy_mod.listar_transactions("acc-1")

    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "PLUGGY_TRANSACTIONS_FALHOU"
