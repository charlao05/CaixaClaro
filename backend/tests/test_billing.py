"""Testes do billing.checkout (M5).

Cobrem o fluxo principal e a regra dura do contrato:
- GET por externalReference antes de POST, sempre.
- Reuso de payment pendente com QR cacheado.
- Reuso de users.asaas_customer_id local.
- Busca de customer no Asaas antes de criar.
- Claim persistente como exclusao mutua.

Mock em services.asaas (nao em HTTP). Banco real.
"""
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from caixaclaro.db import conexao
from caixaclaro.services import asaas as asaas_mod
from caixaclaro.services import billing


async def _criar_usuario(client, email, cpf):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    async with conexao() as conn:
        uid = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
    return uid


def _mock_asaas(
    monkeypatch,
    *,
    customer_existente=None,
    customer_criado_id="cus_novo",
    pagamento_existente=None,
    pagamento_criado_id="pay_novo",
    qr_imagem="base64img",
    qr_payload="000201...",
):
    chamadas = {
        "buscar_customer": [],
        "criar_customer": [],
        "buscar_pagamento": [],
        "criar_pagamento": [],
        "qrcode": [],
    }

    async def buscar_customer(cpf):
        chamadas["buscar_customer"].append(cpf)
        return customer_existente

    async def criar_customer(nome, cpf, email):
        chamadas["criar_customer"].append((nome, cpf, email))
        return {"id": customer_criado_id}

    async def buscar_pagamento(ref):
        chamadas["buscar_pagamento"].append(ref)
        return pagamento_existente

    async def criar_pagamento(
        customer_id, valor, external_reference, descricao, due_date
    ):
        chamadas["criar_pagamento"].append(
            {
                "customer_id": customer_id,
                "valor": valor,
                "external_reference": external_reference,
                "descricao": descricao,
                "due_date": due_date,
            }
        )
        return {"id": pagamento_criado_id, "externalReference": external_reference}

    async def buscar_qrcode(payment_id):
        chamadas["qrcode"].append(payment_id)
        return {"encodedImage": qr_imagem, "payload": qr_payload}

    monkeypatch.setattr(asaas_mod, "buscar_customer_por_cpf", buscar_customer)
    monkeypatch.setattr(asaas_mod, "criar_customer", criar_customer)
    monkeypatch.setattr(
        asaas_mod, "buscar_pagamento_por_external_reference", buscar_pagamento
    )
    monkeypatch.setattr(asaas_mod, "criar_pagamento_pix", criar_pagamento)
    monkeypatch.setattr(asaas_mod, "buscar_pix_qrcode", buscar_qrcode)
    return chamadas


async def _checkout(conn, user_id, plano="pro_mensal", worker="w1"):
    async with conn.transaction():
        return await billing.checkout(conn, user_id, plano, worker)


async def test_checkout_cria_customer_e_payment_e_retorna_qr(client, monkeypatch):
    uid = await _criar_usuario(client, "b1@x.com", "111.111.111-11")
    chamadas = _mock_asaas(monkeypatch)

    async with conexao() as conn:
        out = await _checkout(conn, uid)

    assert out["status"] == "pendente"
    assert out["pix_qr_code"] == "base64img"
    assert out["pix_copy_paste"] == "000201..."

    # customer: GET vazio -> POST
    assert len(chamadas["buscar_customer"]) == 1
    assert len(chamadas["criar_customer"]) == 1

    # payment: GET por externalReference vazio -> POST
    assert len(chamadas["buscar_pagamento"]) == 1
    assert len(chamadas["criar_pagamento"]) == 1

    # QR buscado uma vez
    assert chamadas["qrcode"] == ["pay_novo"]

    # Persistencia local
    async with conexao() as conn:
        row = await conn.fetchrow(
            "SELECT asaas_payment_id, pix_qr_code, pix_copy_paste, "
            "       external_reference, claimed_at "
            "  FROM payments WHERE user_id = $1",
            uid,
        )
    assert row["asaas_payment_id"] == "pay_novo"
    assert row["pix_qr_code"] == "base64img"
    assert row["pix_copy_paste"] == "000201..."
    assert row["external_reference"] is not None
    assert row["claimed_at"] is None  # liberado no finally


async def test_checkout_reusa_customer_local_sem_chamar_asaas(client, monkeypatch):
    uid = await _criar_usuario(client, "b2@x.com", "222.222.222-22")
    chamadas = _mock_asaas(monkeypatch)

    async with conexao() as conn:
        await conn.execute(
            "UPDATE users SET asaas_customer_id = 'cus_existente' WHERE id = $1",
            uid,
        )
        out = await _checkout(conn, uid)

    assert out["status"] == "pendente"
    # Nao consultou nem criou customer
    assert chamadas["buscar_customer"] == []
    assert chamadas["criar_customer"] == []
    # Usou o local
    assert chamadas["criar_pagamento"][0]["customer_id"] == "cus_existente"


async def test_checkout_busca_customer_asaas_antes_de_criar(client, monkeypatch):
    uid = await _criar_usuario(client, "b3@x.com", "333.333.333-33")
    chamadas = _mock_asaas(
        monkeypatch, customer_existente={"id": "cus_achado"}
    )

    async with conexao() as conn:
        await _checkout(conn, uid)

    # GET encontrou -> sem POST
    assert len(chamadas["buscar_customer"]) == 1
    assert chamadas["criar_customer"] == []

    async with conexao() as conn:
        salvo = await conn.fetchval(
            "SELECT asaas_customer_id FROM users WHERE id = $1", uid
        )
    assert salvo == "cus_achado"


async def test_checkout_adota_pagamento_existente_sem_post(client, monkeypatch):
    uid = await _criar_usuario(client, "b4@x.com", "444.444.444-44")
    chamadas = _mock_asaas(
        monkeypatch,
        pagamento_existente={"id": "pay_ja_existe", "externalReference": "x"},
    )

    async with conexao() as conn:
        out = await _checkout(conn, uid)

    # GET encontrou -> sem POST
    assert len(chamadas["buscar_pagamento"]) == 1
    assert chamadas["criar_pagamento"] == []
    # Adotou o ID externo
    assert out["pix_qr_code"] == "base64img"
    assert chamadas["qrcode"] == ["pay_ja_existe"]


async def test_checkout_reusa_payment_pendente_com_qr_cacheado(client, monkeypatch):
    uid = await _criar_usuario(client, "b5@x.com", "555.555.555-55")
    chamadas = _mock_asaas(monkeypatch)

    async with conexao() as conn:
        out1 = await _checkout(conn, uid)
        out2 = await _checkout(conn, uid)

    # Segunda chamada nao toca o Asaas
    assert len(chamadas["criar_pagamento"]) == 1
    assert out1["payment_id"] == out2["payment_id"]
    assert out2["pix_qr_code"] == "base64img"


async def test_checkout_claim_em_andamento_409(client, monkeypatch):
    uid = await _criar_usuario(client, "b6@x.com", "666.666.666-66")
    _mock_asaas(monkeypatch)

    async with conexao() as conn:
        await conn.execute(
            "UPDATE users SET asaas_customer_id = 'cus_x' WHERE id = $1", uid
        )
        # Pre-insere payment pendente com claim tomado por outro worker
        await conn.execute(
            """
            INSERT INTO payments
              (user_id, plano, valor, periodo_dias, status,
               claimed_at, claimed_by, external_reference)
            VALUES ($1, 'pro_mensal', 49.90, 30, 'pendente',
                    now(), 'outro', $2)
            """,
            uid,
            str(uuid.uuid4()),
        )

        with pytest.raises(HTTPException) as exc:
            await _checkout(conn, uid)

    assert exc.value.status_code == 409
    assert exc.value.detail["erro"] == "CHECKOUT_EM_ANDAMENTO"


async def test_checkout_plano_invalido_400(client, monkeypatch):
    uid = await _criar_usuario(client, "b7@x.com", "777.777.777-77")
    _mock_asaas(monkeypatch)

    async with conexao() as conn:
        with pytest.raises(HTTPException) as exc:
            await _checkout(conn, uid, plano="plano_inexistente")

    assert exc.value.status_code == 400
    assert exc.value.detail["erro"] == "PLANO_INVALIDO"
