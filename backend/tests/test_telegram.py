"""Bateria M7 — vinculacao Telegram por token (CONTRATO_API §Telegram)."""
import uuid
from datetime import datetime, timedelta, timezone

from caixaclaro.db import conexao


async def _registrar(client, email, cpf):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "SenhaForte123!", "cpf": cpf},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    token = body["token"]
    async with conexao() as conn:
        uid = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
    return token, str(uid)


async def _gerar_token(client, token_jwt):
    return await client.post(
        "/api/v1/telegram/token-vinculacao",
        headers={"Authorization": f"Bearer {token_jwt}"},
    )


async def _webhook(client, update_id, text, chat_id):
    return await client.post(
        "/api/v1/webhooks/telegram",
        json={
            "update_id": update_id,
            "message": {
                "text": text,
                "chat": {"id": chat_id},
            },
        },
    )


async def test_telegram_token_unico_ativo(client):
    token_jwt, uid = await _registrar(
        client, "tg1@x.com", "341.341.341-41"
    )

    r1 = await _gerar_token(client, token_jwt)
    assert r1.status_code == 200, r1.text
    t1 = r1.json()["token"]

    r2 = await _gerar_token(client, token_jwt)
    assert r2.status_code == 200, r2.text
    t2 = r2.json()["token"]
    assert t1 != t2

    async with conexao() as conn:
        ativos = await conn.fetch(
            """
            SELECT token FROM telegram_link_tokens
             WHERE user_id = $1 AND ativo = TRUE
            """,
            uuid.UUID(uid),
        )
    assert len(ativos) == 1
    assert ativos[0]["token"] == t2


async def test_telegram_vincula_chat_por_start(client):
    token_jwt, uid = await _registrar(
        client, "tg2@x.com", "342.342.342-42"
    )

    r = await _gerar_token(client, token_jwt)
    token = r.json()["token"]

    r = await _webhook(
        client, update_id=1001, text=f"/start {token}", chat_id=55555
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["vinculado"]["user_id"] == uid
    assert body["vinculado"]["vinculado"] is True

    async with conexao() as conn:
        chat = await conn.fetchval(
            "SELECT telegram_chat_id FROM users WHERE id = $1",
            uuid.UUID(uid),
        )
        ativos = await conn.fetchval(
            """
            SELECT count(*) FROM telegram_link_tokens
             WHERE user_id = $1 AND ativo = TRUE
            """,
            uuid.UUID(uid),
        )
    assert chat == 55555
    assert ativos == 0


async def test_telegram_token_expirado_400(client):
    token_jwt, uid = await _registrar(
        client, "tg3@x.com", "343.343.343-43"
    )

    r = await _gerar_token(client, token_jwt)
    token = r.json()["token"]

    # Forca expiracao no passado
    async with conexao() as conn:
        await conn.execute(
            """
            UPDATE telegram_link_tokens
               SET expira_em = $1
             WHERE user_id = $2 AND ativo = TRUE
            """,
            datetime.now(timezone.utc) - timedelta(minutes=1),
            uuid.UUID(uid),
        )

    r = await _webhook(
        client, update_id=1003, text=f"/start {token}", chat_id=55557
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "TELEGRAM_TOKEN_INVALIDO"

    async with conexao() as conn:
        chat = await conn.fetchval(
            "SELECT telegram_chat_id FROM users WHERE id = $1",
            uuid.UUID(uid),
        )
    assert chat is None


async def test_telegram_token_invalido_400(client):
    await _registrar(client, "tg4@x.com", "344.344.344-44")

    r = await _webhook(
        client, update_id=1004, text="/start token-que-nao-existe", chat_id=55558
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "TELEGRAM_TOKEN_INVALIDO"


async def test_telegram_start_sem_token_ignorado(client):
    await _registrar(client, "tg5@x.com", "345.345.345-45")

    r = await _webhook(client, update_id=1005, text="/start", chat_id=55559)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "ignorado": "sem_token"}


async def test_telegram_update_id_duplicado_nao_reprocessa(client):
    token_jwt, uid = await _registrar(
        client, "tg6@x.com", "346.346.346-46"
    )

    r = await _gerar_token(client, token_jwt)
    token = r.json()["token"]

    r1 = await _webhook(
        client, update_id=1006, text=f"/start {token}", chat_id=55560
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True

    r2 = await _webhook(
        client, update_id=1006, text=f"/start {token}", chat_id=55560
    )
    assert r2.status_code == 200
    assert r2.json() == {"ok": True, "duplicado": True}


async def test_telegram_webhook_sem_update_id_400(client):
    r = await client.post(
        "/api/v1/webhooks/telegram",
        json={"message": {"text": "/start x", "chat": {"id": 1}}},
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "WEBHOOK_PAYLOAD_INVALIDO"


async def test_telegram_gerar_token_sem_jwt_401(client):
    r = await client.post("/api/v1/telegram/token-vinculacao")
    assert r.status_code == 401
