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


