"""Bateria C — vinculo clientUserId -> user_id via Pluggy Sandbox.

Fluxo:
  1. registra usuario de teste no backend (ASGI, sem servidor)
  2. autentica na Pluggy e obtem API key
  3. cria Item Sandbox (connectorId=2) com clientUserId=user_id
  4. aguarda o Item sair de UPDATING
  5. envia webhook item/created simulado ao backend
  6. verifica DB: consents, accounts, sync_requests, webhook_events

Uso (a partir de backend/):
  python -m scripts.bateria_c

Requer PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET em .env.
Nao roda em CI: depende de credencial e rede externas.

Do host Windows, se o .env usa o hostname interno "db":
  $env:DATABASE_URL="postgresql://caixaclaro:dev_only_change_me@localhost:5432/caixaclaro"
"""
import asyncio
import sys
import time
import uuid

import httpx
from httpx import ASGITransport

from caixaclaro.config import settings
from caixaclaro.db import conexao
from caixaclaro.main import criar_app

SANDBOX_CONNECTOR_ID = 2
SANDBOX_USER = "user-ok"
SANDBOX_PASSWORD = "password-ok"

PLUGGY_TIMEOUT = 30.0
POLL_INTERVAL = 2.0
POLL_TIMEOUT = 60.0


def _cpf_sintetico() -> str:
    d = str(int(uuid.uuid4().hex, 16) % 10)
    return f"{d*3}.{d*3}.{d*3}-{d*2}"


async def _criar_usuario(client: httpx.AsyncClient) -> str:
    sufixo = uuid.uuid4().hex[:8]
    email = f"bateria-c-{sufixo}@example.com"
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": _cpf_sintetico()},
    )
    if r.status_code != 201:
        raise SystemExit(f"register falhou: {r.status_code} {r.text}")
    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
    return str(user_id)


async def _pluggy_api_key(client: httpx.AsyncClient) -> str:
    s = settings()
    if not s.pluggy_client_id or not s.pluggy_client_secret:
        raise SystemExit(
            "PLUGGY_CLIENT_ID/PLUGGY_CLIENT_SECRET ausentes em .env."
        )
    r = await client.post(
        "/auth",
        json={
            "clientId": s.pluggy_client_id,
            "clientSecret": s.pluggy_client_secret,
        },
    )
    if r.status_code != 200:
        raise SystemExit(f"Pluggy /auth falhou: {r.status_code} {r.text}")
    return r.json()["apiKey"]


async def _criar_item(
    client: httpx.AsyncClient, api_key: str, user_id: str
) -> str:
    r = await client.post(
        "/items",
        headers={"X-API-KEY": api_key},
        json={
            "connectorId": SANDBOX_CONNECTOR_ID,
            "parameters": {
                "user": SANDBOX_USER,
                "password": SANDBOX_PASSWORD,
            },
            "clientUserId": user_id,
        },
    )
    if r.status_code not in (200, 201):
        raise SystemExit(f"Pluggy /items falhou: {r.status_code} {r.text}")
    return r.json()["id"]


async def _aguardar_item(
    client: httpx.AsyncClient, api_key: str, item_id: str
) -> str:
    deadline = time.monotonic() + POLL_TIMEOUT
    while True:
        r = await client.get(
            f"/items/{item_id}", headers={"X-API-KEY": api_key}
        )
        if r.status_code != 200:
            raise SystemExit(
                f"Pluggy GET /items/{item_id} falhou: {r.status_code}"
            )
        status = r.json().get("status")
        if status != "UPDATING":
            return status
        if time.monotonic() > deadline:
            raise SystemExit(
                f"timeout aguardando item (ultimo status: {status})"
            )
        await asyncio.sleep(POLL_INTERVAL)


async def _main() -> int:
    app = criar_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as backend:
            user_id = await _criar_usuario(backend)
            print(f"[1/5] usuario criado: {user_id}")

            s = settings()
            async with httpx.AsyncClient(
                base_url=s.pluggy_base_url, timeout=PLUGGY_TIMEOUT
            ) as pluggy:
                api_key = await _pluggy_api_key(pluggy)
                print("[2/5] API key Pluggy obtida")

                item_id = await _criar_item(pluggy, api_key, user_id)
                print(f"[3/5] Item Sandbox criado: {item_id}")

                status = await _aguardar_item(pluggy, api_key, item_id)
                print(f"[4/5] Item status final: {status}")

            event_id = f"bateria-c-{uuid.uuid4().hex}"
            r = await backend.post(
                "/api/v1/webhooks/pluggy",
                json={
                    "event": "item/created",
                    "eventId": event_id,
                    "itemId": item_id,
                    "clientUserId": user_id,
                },
            )
            if r.status_code != 200:
                print(f"FAIL webhook: {r.status_code} {r.text}")
                return 1
            print(f"[5/5] webhook processado: {r.json()}")

            uid = uuid.UUID(user_id)
            async with conexao() as conn:
                consents = await conn.fetchval(
                    "SELECT count(*) FROM consents "
                    "WHERE user_id = $1 AND provider = 'pluggy'",
                    uid,
                )
                accounts = await conn.fetchval(
                    "SELECT count(*) FROM accounts "
                    "WHERE user_id = $1 AND provider = 'pluggy'",
                    uid,
                )
                syncs = await conn.fetchval(
                    "SELECT count(*) FROM sync_requests WHERE user_id = $1",
                    uid,
                )
                webhook = await conn.fetchval(
                    "SELECT count(*) FROM webhook_events "
                    "WHERE origem = 'pluggy' AND event_id = $1",
                    event_id,
                )

            print()
            print("=== RESULTADO BATERIA C ===")
            print(f"  consents:       {consents}")
            print(f"  accounts:       {accounts}")
            print(f"  sync_requests:  {syncs}")
            print(f"  webhook_events: {webhook}")

            ok = (
                consents >= 1
                and accounts >= 1
                and syncs >= 1
                and webhook == 1
            )
            print(f"  PASS: {ok}")
            return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
