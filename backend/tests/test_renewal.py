"""Bateria M6 — 6 comportamentos de renewal (CONTRATOS_INTERNOS §12)."""
from datetime import date, timedelta

import httpx
import pytest

from caixaclaro.db import conexao
from caixaclaro.services import renewal


async def _criar_usuario(client, email, cpf):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "SenhaForte123!", "cpf": cpf},
    )
    assert r.status_code == 201, r.text
    async with conexao() as conn:
        uid = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
    return uid


async def _criar_subscription(conn, user_id, periodo_fim, pausada_ate=None):
    row = await conn.fetchrow(
        """
        INSERT INTO subscriptions
          (user_id, plano, status, periodo_inicio, periodo_fim, pausada_ate)
        VALUES ($1, 'pro_mensal', 'ativa', now(), $2, $3)
        RETURNING id
        """,
        user_id,
        periodo_fim,
        pausada_ate,
    )
    return row["id"]


def _mock_asaas(monkeypatch, posts, network_error=False):
    async def criar(*args, **kwargs):
        posts.append(kwargs)
        if network_error:
            raise httpx.ConnectError("rede indisponivel")
        return {"id": f"pay-{len(posts)}"}

    async def buscar_ref(ref):
        return None

    async def buscar_qr(payment_id):
        return {
            "encodedImage": f"qr-{payment_id}",
            "payload": f"pix-{payment_id}",
        }

    async def customer(conn, user_id):
        return "cus-renewal"

    monkeypatch.setattr(renewal.asaas, "criar_pagamento_pix", criar)
    monkeypatch.setattr(
        renewal.asaas, "buscar_pagamento_por_external_reference", buscar_ref
    )
    monkeypatch.setattr(renewal.asaas, "buscar_pix_qrcode", buscar_qr)
    monkeypatch.setattr(renewal.billing, "_resolver_customer", customer)


async def test_m6_1_vencida_exatamente_uma_cobranca(client, monkeypatch):
    user_id = await _criar_usuario(client, "renewal1@x.com", "331.331.331-31")

    async with conexao() as conn:
        sub_id = await _criar_subscription(
            conn, user_id, date.today() - timedelta(days=1)
        )
        posts = []
        _mock_asaas(monkeypatch, posts)

        resultado = await renewal.renovar_uma(conn, sub_id, "w1")
        assert resultado["status"] == "cobrado"
        assert len(posts) == 1

        quantidade = await conn.fetchval(
            "SELECT count(*) FROM payments WHERE user_id = $1 AND plano = 'pro_mensal'",
            user_id,
        )
    assert quantidade == 1


async def test_m6_2_rodar_duas_vezes_mantem_uma_cobranca(client, monkeypatch):
    user_id = await _criar_usuario(client, "renewal2@x.com", "332.332.332-32")

    async with conexao() as conn:
        sub_id = await _criar_subscription(
            conn, user_id, date.today() - timedelta(days=1)
        )
        posts = []
        _mock_asaas(monkeypatch, posts)

        primeira = await renewal.renovar_uma(conn, sub_id, "w1")
        segunda = await renewal.renovar_uma(conn, sub_id, "w1")

        assert primeira["status"] == "cobrado"
        assert segunda["status"] == "skip"
        assert len(posts) == 1

        quantidade = await conn.fetchval(
            "SELECT count(*) FROM payments WHERE user_id = $1 AND plano = 'pro_mensal'",
            user_id,
        )
    assert quantidade == 1


async def test_m6_3_payment_expirado_permite_nova_cobranca(client, monkeypatch):
    user_id = await _criar_usuario(client, "renewal3@x.com", "333.333.331-33")

    async with conexao() as conn:
        sub_id = await _criar_subscription(
            conn, user_id, date.today() - timedelta(days=1)
        )
        await conn.execute(
            """
            INSERT INTO payments
              (user_id, plano, valor, periodo_dias, status, expira_em)
            VALUES ($1, 'pro_mensal', 49.90, 30, 'pendente',
                    now() - interval '1 hour')
            """,
            user_id,
        )

        posts = []
        _mock_asaas(monkeypatch, posts)

        resultado = await renewal.renovar_uma(conn, sub_id, "w1")
        assert resultado["status"] == "cobrado"
        assert len(posts) == 1

        quantidade = await conn.fetchval(
            "SELECT count(*) FROM payments WHERE user_id = $1",
            user_id,
        )
    assert quantidade == 2


async def test_m6_4_pausa_vigente_nao_cobra(client, monkeypatch):
    user_id = await _criar_usuario(client, "renewal4@x.com", "334.334.334-34")

    async with conexao() as conn:
        sub_id = await _criar_subscription(
            conn,
            user_id,
            date.today() - timedelta(days=1),
            date.today() + timedelta(days=5),
        )
        posts = []
        _mock_asaas(monkeypatch, posts)

        resultado = await renewal.renovar_uma(conn, sub_id, "w1")
        assert resultado["status"] == "skip"
        assert len(posts) == 0

        quantidade = await conn.fetchval(
            "SELECT count(*) FROM payments WHERE user_id = $1", user_id
        )
    assert quantidade == 0


async def test_m6_5_pausa_expirada_cobra(client, monkeypatch):
    user_id = await _criar_usuario(client, "renewal5@x.com", "335.335.335-35")

    async with conexao() as conn:
        sub_id = await _criar_subscription(
            conn,
            user_id,
            date.today() - timedelta(days=1),
            date.today() - timedelta(days=1),
        )
        posts = []
        _mock_asaas(monkeypatch, posts)

        resultado = await renewal.renovar_uma(conn, sub_id, "w1")
        assert resultado["status"] == "cobrado"
        assert len(posts) == 1


async def test_m6_6_falha_rede_vai_para_reconciliacao(client, monkeypatch):
    user_id = await _criar_usuario(client, "renewal6@x.com", "336.336.336-36")

    async with conexao() as conn:
        sub_id = await _criar_subscription(
            conn, user_id, date.today() - timedelta(days=1)
        )
        posts = []
        _mock_asaas(monkeypatch, posts, network_error=True)

        with pytest.raises(httpx.HTTPError):
            await renewal.renovar_uma(conn, sub_id, "w1")

        assert len(posts) == 1
        status = await conn.fetchval(
            """
            SELECT status FROM payments
             WHERE user_id = $1
             ORDER BY criado_em DESC LIMIT 1
            """,
            user_id,
        )
    assert status == "pendente_reconciliacao"
