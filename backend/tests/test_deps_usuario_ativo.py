"""Testes de api.deps.usuario_ativo - E1.

Chamam usuario_ativo direto (nao via HTTP de produto), porque o gate
das rotas so entra na etapa 3.4. O 'client' fixture serve para:
- garantir que o pool global esteja vivo;
- registrar usuario e obter um 'u' via usuario_atual.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from caixaclaro.db import conexao
from caixaclaro.api.deps import usuario_ativo
from caixaclaro.security.auth import usuario_atual


async def _registrar_u(client, email):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha_segura_123", "cpf": "52998224725"},
    )
    assert r.status_code == 201
    token = r.json()["token"]
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return await usuario_atual(cred)


async def _reler_u(user_id):
    async with conexao() as conn:
        return await conn.fetchrow(
            "SELECT criado_em, trial_exempt FROM users WHERE id = $1",
            user_id,
        )


async def _envelhecer_usuario(user_id, dias):
    async with conexao() as conn:
        await conn.execute(
            "UPDATE users SET criado_em = now() - ($2 || ' days')::interval "
            "WHERE id = $1",
            user_id,
            str(dias),
        )


async def _criar_subscription(user_id, *, periodo_fim):
    async with conexao() as conn:
        await conn.execute(
            "INSERT INTO subscriptions (user_id, plano, status, periodo_fim) "
            "VALUES ($1, 'mensal', 'ativa', $2)",
            user_id,
            periodo_fim,
        )


async def test_trial_vigente_passa(client):
    u = await _registrar_u(client, "tv@x.com")
    resultado = await usuario_ativo(u=u)
    assert resultado["id"] == u["id"]


async def test_trial_expirado_sem_assinatura_402(client):
    u = await _registrar_u(client, "te@x.com")
    await _envelhecer_usuario(u["id"], dias=30)

    row = await _reler_u(u["id"])
    u = {**u, "criado_em": row["criado_em"], "trial_exempt": row["trial_exempt"]}

    with pytest.raises(HTTPException) as exc:
        await usuario_ativo(u=u)
    assert exc.value.status_code == 402
    assert exc.value.detail["erro"] == "ACESSO_BLOQUEADO"
    assert exc.value.detail["estado"] == "trial_expirado"


async def test_trial_expirado_com_assinatura_vigente_passa(client):
    u = await _registrar_u(client, "tv2@x.com")
    await _envelhecer_usuario(u["id"], dias=30)
    await _criar_subscription(
        u["id"], periodo_fim=datetime.now(timezone.utc) + timedelta(days=10)
    )

    row = await _reler_u(u["id"])
    u = {**u, "criado_em": row["criado_em"], "trial_exempt": row["trial_exempt"]}

    resultado = await usuario_ativo(u=u)
    assert resultado["id"] == u["id"]


async def test_trial_expirado_assinatura_vencida_402(client):
    u = await _registrar_u(client, "tv3@x.com")
    await _envelhecer_usuario(u["id"], dias=30)
    await _criar_subscription(
        u["id"], periodo_fim=datetime.now(timezone.utc) - timedelta(days=1)
    )

    row = await _reler_u(u["id"])
    u = {**u, "criado_em": row["criado_em"], "trial_exempt": row["trial_exempt"]}

    with pytest.raises(HTTPException) as exc:
        await usuario_ativo(u=u)
    assert exc.value.status_code == 402
    assert exc.value.detail["estado"] == "assinatura_expirada"


async def test_trial_exempt_passa_mesmo_com_tudo_expirado(client):
    u = await _registrar_u(client, "ex@x.com")
    await _envelhecer_usuario(u["id"], dias=365)
    async with conexao() as conn:
        await conn.execute(
            "UPDATE users SET trial_exempt = TRUE WHERE id = $1", u["id"]
        )

    row = await _reler_u(u["id"])
    u = {**u, "criado_em": row["criado_em"], "trial_exempt": row["trial_exempt"]}

    resultado = await usuario_ativo(u=u)
    assert resultado["id"] == u["id"]