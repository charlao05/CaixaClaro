"""Testes de recuperacao de senha via Telegram — M12.

Cobre: indistinguibilidade da resposta, envio best-effort ao Telegram,
rate limit, uso unico do codigo, revogacao de sessoes apos reset.
"""
import uuid as _uuid

from caixaclaro.db import conexao
from caixaclaro.services import senha, telegram_bot
from tests._cpf import cpf_valido


async def _registrar(client, prefix: str, com_telegram: bool = False):
    """Retorna (token, user_id). Se com_telegram, seta chat_id no banco."""
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{prefix}@x.com",
            "senha": "senha_segura_123",
            "cpf": cpf_valido(str(_uuid.uuid4().int)[:9]),
        },
    )
    assert r.status_code == 201, r.json()
    body = r.json()
    if com_telegram:
        async with conexao() as conn:
            await conn.execute(
                "UPDATE users SET telegram_chat_id = $1 WHERE id = $2",
                123456789,
                _uuid.UUID(body["user"]["id"]),
            )
    return body["token"], body["user"]["id"]


async def test_esqueci_senha_sem_telegram_retorna_202(client):
    await _registrar(client, "esq-sem-tg", com_telegram=False)
    r = await client.post(
        "/api/v1/auth/esqueci-senha",
        json={"email": "esq-sem-tg@x.com"},
    )
    assert r.status_code == 202, r.json()
    assert r.json() == {"ok": True}


async def test_esqueci_senha_email_inexistente_retorna_202(client):
    r = await client.post(
        "/api/v1/auth/esqueci-senha",
        json={"email": "nao_existe_zz@x.com"},
    )
    assert r.status_code == 202
    assert r.json() == {"ok": True}


async def test_esqueci_senha_com_telegram_envia(client, monkeypatch):
    enviadas = []

    async def fake_envio(chat_id, texto):
        enviadas.append((chat_id, texto))
        return {"ok": True}

    monkeypatch.setattr(telegram_bot, "enviar_mensagem", fake_envio)

    await _registrar(client, "esq-tg", com_telegram=True)
    r = await client.post(
        "/api/v1/auth/esqueci-senha",
        json={"email": "esq-tg@x.com"},
    )
    assert r.status_code == 202
    assert len(enviadas) == 1
    chat_id, texto = enviadas[0]
    assert chat_id == 123456789
    assert "codigo" in texto.lower() or "código" in texto.lower()


async def test_esqueci_senha_telegram_falha_ainda_202(client, monkeypatch, caplog):
    marcador = "TEXTO_DE_ERRO_DE_TESTE"
    async def fake_falha(chat_id, texto):
        raise RuntimeError(marcador)

    monkeypatch.setattr(telegram_bot, "enviar_mensagem", fake_falha)
    await _registrar(client, "esq-falha", com_telegram=True)
    r = await client.post(
        "/api/v1/auth/esqueci-senha",
        json={"email": "esq-falha@x.com"},
    )
    assert r.status_code == 202
    assert "reset_telegram_send_failed" in caplog.text
    assert marcador not in caplog.text


async def test_esqueci_senha_rate_limit(client):
    for i in range(5):
        r = await client.post(
            "/api/v1/auth/esqueci-senha",
            json={"email": f"spam_{i}@x.com"},
        )
        assert r.status_code == 202
    r = await client.post(
        "/api/v1/auth/esqueci-senha",
        json={"email": "spam_final@x.com"},
    )
    assert r.status_code == 429


async def test_redefinir_senha_sucesso(client, monkeypatch):
    monkeypatch.setattr(senha, "_gerar_codigo", lambda: "123456")
    await _registrar(client, "reset-ok", com_telegram=True)

    r = await client.post(
        "/api/v1/auth/esqueci-senha",
        json={"email": "reset-ok@x.com"},
    )
    assert r.status_code == 202

    r = await client.post(
        "/api/v1/auth/redefinir-senha",
        json={
            "email": "reset-ok@x.com",
            "codigo": "123456",
            "nova_senha": "nova_senha_456",
        },
    )
    assert r.status_code == 200, r.json()
    assert r.json() == {"ok": True}

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset-ok@x.com", "senha": "nova_senha_456"},
    )
    assert r.status_code == 200

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset-ok@x.com", "senha": "senha_segura_123"},
    )
    assert r.status_code == 401


async def test_redefinir_senha_codigo_invalido_400(client):
    await _registrar(client, "reset-inv")
    r = await client.post(
        "/api/v1/auth/redefinir-senha",
        json={
            "email": "reset-inv@x.com",
            "codigo": "999999",
            "nova_senha": "nova_senha_456",
        },
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "CODIGO_INVALIDO"


async def test_redefinir_senha_email_inexistente_400(client):
    r = await client.post(
        "/api/v1/auth/redefinir-senha",
        json={
            "email": "fantasma_zz@x.com",
            "codigo": "123456",
            "nova_senha": "nova_senha_456",
        },
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "CODIGO_INVALIDO"


async def test_redefinir_senha_codigo_ja_usado_400(client, monkeypatch):
    monkeypatch.setattr(senha, "_gerar_codigo", lambda: "123456")
    await _registrar(client, "reset-duplo", com_telegram=True)

    await client.post(
        "/api/v1/auth/esqueci-senha",
        json={"email": "reset-duplo@x.com"},
    )

    r = await client.post(
        "/api/v1/auth/redefinir-senha",
        json={
            "email": "reset-duplo@x.com",
            "codigo": "123456",
            "nova_senha": "nova_senha_456",
        },
    )
    assert r.status_code == 200

    r = await client.post(
        "/api/v1/auth/redefinir-senha",
        json={
            "email": "reset-duplo@x.com",
            "codigo": "123456",
            "nova_senha": "outra_senha_789",
        },
    )
    assert r.status_code == 400


async def test_redefinir_senha_revoga_sessoes(client, monkeypatch):
    monkeypatch.setattr(senha, "_gerar_codigo", lambda: "123456")
    token_antigo, _ = await _registrar(client, "reset-revoga", com_telegram=True)

    r = await client.get(
        "/api/v1/perfil",
        headers={"Authorization": f"Bearer {token_antigo}"},
    )
    assert r.status_code == 200

    await client.post(
        "/api/v1/auth/esqueci-senha",
        json={"email": "reset-revoga@x.com"},
    )
    r = await client.post(
        "/api/v1/auth/redefinir-senha",
        json={
            "email": "reset-revoga@x.com",
            "codigo": "123456",
            "nova_senha": "nova_senha_456",
        },
    )
    assert r.status_code == 200

    r = await client.get(
        "/api/v1/perfil",
        headers={"Authorization": f"Bearer {token_antigo}"},
    )
    assert r.status_code == 401


async def test_redefinir_senha_curta_422(client):
    await _registrar(client, "reset-curta")
    r = await client.post(
        "/api/v1/auth/redefinir-senha",
        json={
            "email": "reset-curta@x.com",
            "codigo": "123456",
            "nova_senha": "curta",
        },
    )
    assert r.status_code == 422


async def test_redefinir_senha_codigo_formato_invalido_422(client):
    await _registrar(client, "reset-fmt")
    r = await client.post(
        "/api/v1/auth/redefinir-senha",
        json={
            "email": "reset-fmt@x.com",
            "codigo": "abc",
            "nova_senha": "nova_senha_456",
        },
    )
    assert r.status_code == 422