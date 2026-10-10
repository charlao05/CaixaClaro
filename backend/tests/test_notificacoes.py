"""Notificacoes de alertas por Telegram (M7, escopo B).

Verifica que alertas fiscais criados por /colar e /confirmar sao
efetivamente encaminhados ao Telegram quando o usuario tem
telegram_chat_id, e que nada e enviado caso contrario.
"""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

from caixaclaro.db import conexao


async def _registrar_com_chat(
    client, *, email, cpf, chat_id=None
):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "SenhaForte123!", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    token = r.json()["token"]
    async with conexao() as conn:
        uid = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
        if chat_id is not None:
            await conn.execute(
                "UPDATE users SET telegram_chat_id = $1 WHERE id = $2",
                chat_id,
                uid,
            )
    return token, uid


async def _colar(client, token, texto, key=None):
    return await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": key or str(uuid.uuid4()),
        },
        json={"texto": texto},
    )


def _mock_enviar(monkeypatch):
    enviar = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        "caixaclaro.services.notificacoes.telegram_bot.enviar_mensagem",
        enviar,
    )
    return enviar


async def test_colar_cruza_faixa_envia_telegram(client, monkeypatch):
    """Usuario com chat_id: alerta de faixa e enviado 1x por faixa cruzada."""
    _, uid = await _registrar_com_chat(
        client, email="notif1@x.com", cpf="511.511.511-57", chat_id=90001
    )
    enviar = _mock_enviar(monkeypatch)

    # R$ 50.000 cruza 60% (teto 81.000); uma faixa => 1 mensagem
    r = await _colar(
        client,
        (await _login(client, "notif1@x.com")).json()["token"],
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 50.000,00",
    )
    assert r.status_code == 201, r.json()

    assert enviar.await_count == 1
    chat_arg, msg_arg = enviar.await_args.args
    assert chat_arg == 90001
    assert "60%" in msg_arg and "limite anual" in msg_arg


async def test_colar_sem_chat_nao_envia(client, monkeypatch):
    """Usuario sem telegram_chat_id: nada e enviado."""
    _, _ = await _registrar_com_chat(
        client, email="notif2@x.com", cpf="512.512.512-18", chat_id=None
    )
    enviar = _mock_enviar(monkeypatch)

    r = await _colar(
        client,
        (await _login(client, "notif2@x.com")).json()["token"],
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 50.000,00",
    )
    assert r.status_code == 201
    assert enviar.await_count == 0


async def test_colar_replay_idempotente_envia_uma_vez(client, monkeypatch):
    """Replay com mesma Idempotency-Key nao reenvia Telegram."""
    _, _ = await _registrar_com_chat(
        client, email="notif3@x.com", cpf="513.513.513-89", chat_id=90003
    )
    enviar = _mock_enviar(monkeypatch)
    token = (await _login(client, "notif3@x.com")).json()["token"]
    key = str(uuid.uuid4())
    texto = "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 50.000,00"

    r1 = await _colar(client, token, texto, key=key)
    r2 = await _colar(client, token, texto, key=key)
    assert r1.status_code == 201
    assert r2.status_code == 201

    assert enviar.await_count == 1


async def test_colar_sem_cruzar_faixa_nao_envia(client, monkeypatch):
    """Receita abaixo de 60% nao cria alerta, logo nao envia."""
    _, _ = await _registrar_com_chat(
        client, email="notif4@x.com", cpf="514.514.514-40", chat_id=90004
    )
    enviar = _mock_enviar(monkeypatch)

    # R$ 1.000 = ~1,2% do teto, abaixo de 60%
    r = await _colar(
        client,
        (await _login(client, "notif4@x.com")).json()["token"],
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 1.000,00",
    )
    assert r.status_code == 201
    assert enviar.await_count == 0


async def _login(client, email):
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "senha": "SenhaForte123!"},
    )
