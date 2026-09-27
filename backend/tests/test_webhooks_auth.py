"""Autenticacao dos webhooks - M10a."""


PLUGGY_HEADER = "X-CaixaClaro-Webhook-Secret"
PLUGGY_SECRET = "test-pluggy-secret"
ASAAS_HEADER = "asaas-access-token"
ASAAS_TOKEN = "test-asaas-token"
TELEGRAM_HEADER = "X-Telegram-Bot-Api-Secret-Token"
TELEGRAM_SECRET = "test-telegram-secret"


def _override(monkeypatch, *, pluggy=PLUGGY_SECRET, asaas=ASAAS_TOKEN, telegram=TELEGRAM_SECRET):
    from caixaclaro.api import webhooks as w

    class S:
        pluggy_webhook_secret = pluggy
        asaas_webhook_token = asaas
        telegram_webhook_secret = telegram

    monkeypatch.setattr(w, "settings", lambda: S())


async def test_pluggy_secret_ausente_401(client_sem_auth, monkeypatch):
    _override(monkeypatch, pluggy=None)
    r = await client_sem_auth.post(
        "/api/v1/webhooks/pluggy", json={"event": "item/created"}
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_CONFIGURADO"


async def test_pluggy_header_ausente_401(client_sem_auth):
    r = await client_sem_auth.post(
        "/api/v1/webhooks/pluggy", json={"event": "item/created"}
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_AUTORIZADO"


async def test_pluggy_header_errado_401(client_sem_auth):
    r = await client_sem_auth.post(
        "/api/v1/webhooks/pluggy",
        json={"event": "item/created"},
        headers={PLUGGY_HEADER: "errado"},
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_AUTORIZADO"


async def test_pluggy_body_invalido_sem_header_401_nao_400(client_sem_auth):
    r = await client_sem_auth.post(
        "/api/v1/webhooks/pluggy",
        content=b"nao-e-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_AUTORIZADO"


async def test_pluggy_401_nao_cria_webhook_event(client_sem_auth):
    from caixaclaro.db import conexao

    r = await client_sem_auth.post(
        "/api/v1/webhooks/pluggy", json={"event": "item/created"}
    )
    assert r.status_code == 401
    async with conexao() as conn:
        n = await conn.fetchval(
            "SELECT count(*) FROM webhook_events WHERE origem = 'pluggy'"
        )
    assert n == 0


async def test_asaas_secret_ausente_401(client_sem_auth, monkeypatch):
    _override(monkeypatch, asaas=None)
    r = await client_sem_auth.post(
        "/api/v1/webhooks/asaas", json={"event": "PAYMENT_CONFIRMED"}
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_CONFIGURADO"


async def test_asaas_header_ausente_401(client_sem_auth):
    r = await client_sem_auth.post(
        "/api/v1/webhooks/asaas", json={"event": "PAYMENT_CONFIRMED"}
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_AUTORIZADO"


async def test_asaas_header_errado_401(client_sem_auth):
    r = await client_sem_auth.post(
        "/api/v1/webhooks/asaas",
        json={"event": "PAYMENT_CONFIRMED"},
        headers={ASAAS_HEADER: "errado"},
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_AUTORIZADO"


async def test_asaas_body_invalido_sem_header_401_nao_400(client_sem_auth):
    r = await client_sem_auth.post(
        "/api/v1/webhooks/asaas",
        content=b"nao-e-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401


async def test_telegram_secret_ausente_401(client_sem_auth, monkeypatch):
    _override(monkeypatch, telegram=None)
    r = await client_sem_auth.post(
        "/api/v1/webhooks/telegram", json={"update_id": 1}
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_CONFIGURADO"


async def test_telegram_header_ausente_401(client_sem_auth):
    r = await client_sem_auth.post(
        "/api/v1/webhooks/telegram", json={"update_id": 1}
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_AUTORIZADO"


async def test_telegram_header_errado_401(client_sem_auth):
    r = await client_sem_auth.post(
        "/api/v1/webhooks/telegram",
        json={"update_id": 1},
        headers={TELEGRAM_HEADER: "errado"},
    )
    assert r.status_code == 401
    assert r.json()["erro"] == "WEBHOOK_NAO_AUTORIZADO"


async def test_telegram_body_invalido_sem_header_401_nao_400(client_sem_auth):
    r = await client_sem_auth.post(
        "/api/v1/webhooks/telegram",
        content=b"nao-e-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401
