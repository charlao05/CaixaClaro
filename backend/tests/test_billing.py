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
    pagamento_cartao_id="pay_card_novo",
    invoice_url="https://www.asaas.com/i/pay_card_novo",
    estado_asaas=None,
):
    chamadas = {
        "buscar_customer": [],
        "criar_customer": [],
        "buscar_pagamento": [],
        "criar_pagamento": [],
        "qrcode": [],
        "criar_pagamento_cartao": [],
        "buscar_pagamento_por_id": [],
        "cancelar_pagamento": [],
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

    async def criar_pagamento_cartao(
        customer_id,
        valor,
        external_reference,
        descricao,
        due_date,
        success_url,
    ):
        chamadas["criar_pagamento_cartao"].append(
            {
                "customer_id": customer_id,
                "valor": valor,
                "external_reference": external_reference,
                "descricao": descricao,
                "due_date": due_date,
                "success_url": success_url,
            }
        )
        return {
            "id": pagamento_cartao_id,
            "externalReference": external_reference,
            "invoiceUrl": invoice_url,
        }

    async def buscar_pagamento_por_id(payment_id):
        chamadas["buscar_pagamento_por_id"].append(payment_id)
        return estado_asaas

    async def cancelar_pagamento(payment_id):
        chamadas["cancelar_pagamento"].append(payment_id)
        return None

    monkeypatch.setattr(
        asaas_mod, "criar_pagamento_cartao_avulso", criar_pagamento_cartao
    )
    monkeypatch.setattr(
        asaas_mod, "buscar_pagamento_por_id", buscar_pagamento_por_id
    )
    monkeypatch.setattr(asaas_mod, "cancelar_pagamento", cancelar_pagamento)
    return chamadas


async def _checkout(
    conn, user_id, plano="pro_mensal", worker="w1", metodo="pix"
):
    async with conn.transaction():
        return await billing.checkout(conn, user_id, plano, worker, metodo)


async def test_checkout_cria_customer_e_payment_e_retorna_qr(client, monkeypatch):
    uid = await _criar_usuario(client, "b1@x.com", "111.444.777-35")
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
    uid = await _criar_usuario(client, "b2@x.com", "222.222.220-60")
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
    uid = await _criar_usuario(client, "b3@x.com", "333.333.330-90")
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
    uid = await _criar_usuario(client, "b4@x.com", "444.444.440-10")
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
    uid = await _criar_usuario(client, "b5@x.com", "555.555.550-40")
    chamadas = _mock_asaas(monkeypatch)

    async with conexao() as conn:
        out1 = await _checkout(conn, uid)
        out2 = await _checkout(conn, uid)

    # Segunda chamada nao toca o Asaas
    assert len(chamadas["criar_pagamento"]) == 1
    assert out1["payment_id"] == out2["payment_id"]
    assert out2["pix_qr_code"] == "base64img"


async def test_checkout_claim_em_andamento_409(client, monkeypatch):
    uid = await _criar_usuario(client, "b6@x.com", "666.666.660-70")
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
    uid = await _criar_usuario(client, "b7@x.com", "777.777.770-09")
    _mock_asaas(monkeypatch)

    async with conexao() as conn:
        with pytest.raises(HTTPException) as exc:
            await _checkout(conn, uid, plano="plano_inexistente")

    assert exc.value.status_code == 400
    assert exc.value.detail["erro"] == "PLANO_INVALIDO"


# ----------------------------------------------------------------
# M5.8a — concorrencia e crash
# ----------------------------------------------------------------

async def test_checkout_crash_pos_post_adota_no_retry(client, monkeypatch):
    """Simula: POST Asaas OK, UPDATE local falhou antes de gravar asaas_id.

    Estado deixado: payment pendente com external_reference mas sem
    asaas_payment_id. Proximo checkout faz GET e adota, sem 2o PIX.
    """
    uid = await _criar_usuario(client, "crash@x.com", "311.311.311-34")
    chamadas = _mock_asaas(
        monkeypatch,
        pagamento_existente={"id": "pay_ext_crash", "externalReference": "ref"},
    )

    async with conexao() as conn:
        await conn.execute(
            "UPDATE users SET asaas_customer_id = 'cus_x' WHERE id = $1", uid
        )
        # Estado pos-crash: pendente, external_reference definida, sem asaas_id
        await conn.execute(
            """
            INSERT INTO payments
              (user_id, plano, valor, periodo_dias, status, external_reference)
            VALUES ($1, 'pro_mensal', 49.90, 30, 'pendente', 'ref')
            """,
            uid,
        )

    async with conexao() as conn:
        out = await _checkout(conn, uid)

    # GET encontrou -> adotou, sem segundo POST
    assert chamadas["criar_pagamento"] == []
    assert chamadas["qrcode"] == ["pay_ext_crash"]
    assert out["status"] == "pendente"

    # ID persistido agora
    async with conexao() as conn:
        salvo = await conn.fetchval(
            "SELECT asaas_payment_id FROM payments WHERE user_id = $1", uid
        )
    assert salvo == "pay_ext_crash"


async def test_checkout_corrida_dois_workers_apenas_um_post(client, monkeypatch):
    """Dois checkouts concorrentes: apenas um POST no Asaas.

    O advisory lock por usuario serializa. Task B encontra o payment
    da Task A com QR cacheado e retorna sem tocar o Asaas.
    """
    import asyncio

    uid = await _criar_usuario(client, "corrida@x.com", "312.312.312-03")
    chamadas = _mock_asaas(monkeypatch)

    async def task(worker_id):
        async with conexao() as conn:
            return await _checkout(conn, uid, worker=worker_id)

    r1, r2 = await asyncio.gather(task("w1"), task("w2"))

    # Invariante: nunca dois POSTs
    assert len(chamadas["criar_pagamento"]) == 1

    # Ambos retornam sucesso com o mesmo payment_id local
    assert r1["payment_id"] == r2["payment_id"]
    assert r1["status"] == "pendente"
    assert r2["status"] == "pendente"

    # Claim liberado
    async with conexao() as conn:
        claim = await conn.fetchval(
            "SELECT claimed_at FROM payments WHERE user_id = $1", uid
        )
    assert claim is None


# ----------------------------------------------------------------
# M5 — integração HTTP dos endpoints de billing
# ----------------------------------------------------------------

async def test_http_checkout_com_idempotency_key(client, monkeypatch):
    await _criar_usuario(client, "http-billing@x.com", "313.313.313-66")
    _mock_asaas(monkeypatch)

    # Registrar e obter token pelo padrão existente.
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "http-billing@x.com", "senha": "senha123"},
    )
    assert r.status_code == 200, r.json()
    token = r.json()["token"]

    chave = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/billing/checkout",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": chave,
        },
        json={"plano": "pro_mensal"},
    )

    assert r.status_code == 202, r.json()
    body = r.json()
    assert body["status"] == "pendente"
    assert body["pix_qr_code"] == "base64img"
    assert body["pix_copy_paste"] == "000201..."


async def test_http_checkout_mesma_chave_retorna_mesma_resposta(
    client, monkeypatch
):
    await _criar_usuario(client, "http-idem@x.com", "314.314.314-27")
    chamadas = _mock_asaas(monkeypatch)

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "http-idem@x.com", "senha": "senha123"},
    )
    assert r.status_code == 200, r.json()
    token = r.json()["token"]

    chave = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": chave,
    }

    r1 = await client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plano": "pro_mensal"},
    )
    r2 = await client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plano": "pro_mensal"},
    )

    assert r1.status_code == 202, r1.json()
    assert r2.status_code == 202, r2.json()
    assert r2.json() == r1.json()

    # Segunda chamada não toca novamente o Asaas.
    assert len(chamadas["criar_pagamento"]) == 1


async def test_http_checkout_sem_idempotency_key_422(client):
    await _criar_usuario(client, "http-sem-key@x.com", "315.315.315-98")

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "http-sem-key@x.com", "senha": "senha123"},
    )
    assert r.status_code == 200, r.json()
    token = r.json()["token"]

    r = await client.post(
        "/api/v1/billing/checkout",
        headers={"Authorization": f"Bearer {token}"},
        json={"plano": "pro_mensal"},
    )

    assert r.status_code == 422

# ============================================================
# B.4 — cartao avulso via Invoice
# ============================================================


async def test_checkout_cartao_retorna_invoice_url(client, monkeypatch):
    uid = await _criar_usuario(client, "bc1@x.com", "111.444.777-35")
    chamadas = _mock_asaas(monkeypatch)

    async with conexao() as conn:
        out = await _checkout(conn, uid, metodo="cartao")

    assert out["metodo"] == "cartao"
    assert out["status"] == "pendente"
    assert out["invoice_url"] == "https://www.asaas.com/i/pay_card_novo"
    assert out["pix_qr_code"] is None
    assert out["pix_copy_paste"] is None

    assert len(chamadas["criar_pagamento_cartao"]) == 1
    assert chamadas["criar_pagamento"] == []
    assert chamadas["qrcode"] == []

    from caixaclaro.config import settings
    assert (
        chamadas["criar_pagamento_cartao"][0]["success_url"]
        is None  # Rota 2: FRONTEND_URL localhost omite callback
    )


async def test_checkout_metodo_invalido_400(client, monkeypatch):
    uid = await _criar_usuario(client, "bc2@x.com", "111.444.777-35")
    _mock_asaas(monkeypatch)

    async with conexao() as conn:
        with pytest.raises(HTTPException) as exc:
            await _checkout(conn, uid, metodo="dinheiro")

    assert exc.value.status_code == 400
    assert exc.value.detail["erro"] == "METODO_INVALIDO"


async def test_checkout_cartao_substitui_pix_pendente(client, monkeypatch):
    uid = await _criar_usuario(client, "bc3@x.com", "111.444.777-35")
    async with conexao() as conn:
        pix_id = await conn.fetchval(
            """
            INSERT INTO payments
              (user_id, plano, valor, periodo_dias, status, metodo)
            VALUES ($1, 'pro_mensal', 29.90, 30, 'pendente', 'pix')
            RETURNING id
            """,
            uid,
        )

    chamadas = _mock_asaas(monkeypatch)

    async with conexao() as conn:
        out = await _checkout(conn, uid, metodo="cartao")

    assert out["metodo"] == "cartao"

    async with conexao() as conn:
        pix_status = await conn.fetchval(
            "SELECT status FROM payments WHERE id = $1", pix_id
        )
    assert pix_status == "cancelado"

    # Sem asaas_payment_id, GET/DELETE nao sao chamados.
    assert chamadas["buscar_pagamento_por_id"] == []
    assert chamadas["cancelar_pagamento"] == []


async def test_checkout_pix_substitui_cartao_pendente(client, monkeypatch):
    uid = await _criar_usuario(client, "bc4@x.com", "111.444.777-35")
    async with conexao() as conn:
        cart_id = await conn.fetchval(
            """
            INSERT INTO payments
              (user_id, plano, valor, periodo_dias, status, metodo)
            VALUES ($1, 'pro_mensal', 29.90, 30, 'pendente', 'cartao')
            RETURNING id
            """,
            uid,
        )

    _mock_asaas(monkeypatch)

    async with conexao() as conn:
        out = await _checkout(conn, uid, metodo="pix")

    assert out["metodo"] == "pix"
    assert out["pix_qr_code"] == "base64img"

    async with conexao() as conn:
        cart_status = await conn.fetchval(
            "SELECT status FROM payments WHERE id = $1", cart_id
        )
    assert cart_status == "cancelado"


async def test_substituicao_asaas_pendente_faz_delete(client, monkeypatch):
    uid = await _criar_usuario(client, "bc5@x.com", "111.444.777-35")
    async with conexao() as conn:
        await conn.execute(
            """
            INSERT INTO payments
              (user_id, plano, valor, periodo_dias, status, metodo,
               asaas_payment_id)
            VALUES ($1, 'pro_mensal', 29.90, 30, 'pendente', 'pix', 'pay_x')
            """,
            uid,
        )

    chamadas = _mock_asaas(
        monkeypatch,
        estado_asaas={"id": "pay_x", "status": "PENDING"},
    )

    async with conexao() as conn:
        await _checkout(conn, uid, metodo="cartao")

    assert chamadas["buscar_pagamento_por_id"] == ["pay_x"]
    assert chamadas["cancelar_pagamento"] == ["pay_x"]


async def test_substituicao_asaas_nao_pendente_nao_deleta(
    client, monkeypatch
):
    uid = await _criar_usuario(client, "bc6@x.com", "111.444.777-35")
    async with conexao() as conn:
        await conn.execute(
            """
            INSERT INTO payments
              (user_id, plano, valor, periodo_dias, status, metodo,
               asaas_payment_id)
            VALUES ($1, 'pro_mensal', 29.90, 30, 'pendente', 'pix', 'pay_y')
            """,
            uid,
        )

    chamadas = _mock_asaas(
        monkeypatch,
        estado_asaas={"id": "pay_y", "status": "CONFIRMED"},
    )

    async with conexao() as conn:
        await _checkout(conn, uid, metodo="cartao")

    assert chamadas["buscar_pagamento_por_id"] == ["pay_y"]
    assert chamadas["cancelar_pagamento"] == []  # NAO chamado


async def test_webhook_confirmado_apos_cancelado_concede_periodo(
    client, monkeypatch
):
    uid = await _criar_usuario(client, "bc7@x.com", "111.444.777-35")
    async with conexao() as conn:
        await conn.execute(
            """
            INSERT INTO payments
              (user_id, plano, valor, periodo_dias, status, metodo,
               asaas_payment_id, external_reference)
            VALUES ($1, 'pro_mensal', 29.90, 30, 'cancelado', 'pix',
                    'pay_z', 'ext_z')
            """,
            uid,
        )

    async with conexao() as conn:
        async with conn.transaction():
            res = await billing.processar_webhook_asaas(
                conn,
                {
                    "event": "PAYMENT_CONFIRMED",
                    "payment": {"id": "pay_z", "externalReference": "ext_z"},
                },
            )

    assert res["ok"] is True
    assert res["status"] == "confirmado"

    async with conexao() as conn:
        status = await conn.fetchval(
            "SELECT status FROM payments WHERE asaas_payment_id = 'pay_z'"
        )
        sub = await conn.fetchrow(
            "SELECT plano, periodo_fim FROM subscriptions "
            " WHERE user_id = $1",
            uid,
        )

    assert status == "confirmado"
    assert sub is not None
    assert sub["plano"] == "pro_mensal"


async def test_checkout_cartao_persiste_metodo(client, monkeypatch):
    uid = await _criar_usuario(client, "bc8@x.com", "111.444.777-35")
    _mock_asaas(monkeypatch)

    async with conexao() as conn:
        await _checkout(conn, uid, metodo="cartao")

    async with conexao() as conn:
        row = await conn.fetchrow(
            "SELECT metodo, status FROM payments WHERE user_id = $1",
            uid,
        )

    assert row["metodo"] == "cartao"
    assert row["status"] == "pendente"


# ============================================================
# B.5 — API HTTP do cartao
# ============================================================


async def test_http_checkout_cartao_retorna_invoice_url(client, monkeypatch):
    await _criar_usuario(client, "http-card@x.com", "316.316.316-59")
    chamadas = _mock_asaas(monkeypatch)

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "http-card@x.com", "senha": "senha123"},
    )
    assert r.status_code == 200, r.json()
    token = r.json()["token"]

    chave = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/billing/checkout",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": chave,
        },
        json={"plano": "pro_mensal", "metodo": "cartao"},
    )

    assert r.status_code == 202, r.json()
    body = r.json()
    assert body["metodo"] == "cartao"
    assert body["status"] == "pendente"
    assert body["invoice_url"] == "https://www.asaas.com/i/pay_card_novo"
    assert body["pix_qr_code"] is None
    assert body["pix_copy_paste"] is None

    assert len(chamadas["criar_pagamento_cartao"]) == 1
    assert chamadas["criar_pagamento"] == []
    assert chamadas["qrcode"] == []

    from caixaclaro.config import settings
    assert (
        chamadas["criar_pagamento_cartao"][0]["success_url"]
        is None  # Rota 2: FRONTEND_URL localhost omite callback
    )


async def test_http_checkout_metodo_invalido_422(client, monkeypatch):
    await _criar_usuario(client, "http-bad@x.com", "52998224725")
    _mock_asaas(monkeypatch)

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "http-bad@x.com", "senha": "senha123"},
    )
    assert r.status_code == 200, r.json()
    token = r.json()["token"]

    r = await client.post(
        "/api/v1/billing/checkout",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"plano": "pro_mensal", "metodo": "dinheiro"},
    )

    assert r.status_code == 422

def test_success_url_para_asaas_url_publica(monkeypatch):
    """Rota 2: FRONTEND_URL publico -> helper devolve a URL."""
    from caixaclaro.config import settings
    from caixaclaro.services.billing import _success_url_para_asaas

    monkeypatch.setenv("FRONTEND_URL", "https://app.caixaclaro.com.br")
    settings.cache_clear()
    try:
        assert _success_url_para_asaas() == "https://app.caixaclaro.com.br"
    finally:
        settings.cache_clear()


# ----------------------------------------------------------------
# Revisão de 2026-10-09 (achado R7): voltar no dia seguinte para pagar
# ----------------------------------------------------------------

def _asaas_com_ids_distintos(monkeypatch):
    """Como _mock_asaas, mas cada cobrança criada recebe um id próprio."""
    chamadas = _mock_asaas(monkeypatch)
    criados: list[str] = []

    async def criar_pix(customer_id, valor, external_reference, descricao, due_date):
        asaas_id = f"pay_pix_{len(criados) + 1}"
        criados.append(asaas_id)
        return {"id": asaas_id, "externalReference": external_reference}

    monkeypatch.setattr(asaas_mod, "criar_pagamento_pix", criar_pix)
    chamadas["pix_criados"] = criados
    return chamadas


async def _vencer_prazo_local(uid):
    """Passam mais de 24 h: o pendente sai do prazo local de reuso."""
    async with conexao() as conn:
        await conn.execute(
            "UPDATE payments SET expira_em = now() - interval '1 hour' "
            " WHERE user_id = $1 AND status = 'pendente'",
            uid,
        )


async def _payments(uid):
    async with conexao() as conn:
        rows = await conn.fetch(
            "SELECT id, status, metodo, asaas_payment_id FROM payments "
            " WHERE user_id = $1 ORDER BY criado_em, asaas_payment_id",
            uid,
        )
    return [dict(r) for r in rows]


async def test_checkout_no_dia_seguinte_gera_cobranca_nova(client, monkeypatch):
    uid = await _criar_usuario(client, "r7a@x.com", "111.444.777-35")
    chamadas = _asaas_com_ids_distintos(monkeypatch)

    async with conexao() as conn:
        primeiro = await _checkout(conn, uid)
    await _vencer_prazo_local(uid)
    async with conexao() as conn:
        segundo = await _checkout(conn, uid, worker="w2")

    assert segundo["status"] == "pendente"
    assert segundo["payment_id"] != primeiro["payment_id"]
    assert segundo["pix_copy_paste"] == "000201..."
    assert chamadas["pix_criados"] == ["pay_pix_1", "pay_pix_2"]

    linhas = await _payments(uid)
    assert [(l["status"], l["asaas_payment_id"]) for l in linhas] == [
        ("expirado", "pay_pix_1"),
        ("pendente", "pay_pix_2"),
    ]
    async with conexao() as conn:
        auditado = await conn.fetchval(
            "SELECT alvo FROM audit_log WHERE acao = 'PAGAMENTO_PENDENTE_EXPIRADO'"
        )
    assert auditado == primeiro["payment_id"]


async def test_checkout_no_dia_seguinte_com_cartao(client, monkeypatch):
    uid = await _criar_usuario(client, "r7b@x.com", "222.222.220-60")
    _asaas_com_ids_distintos(monkeypatch)

    async with conexao() as conn:
        await _checkout(conn, uid)
    await _vencer_prazo_local(uid)
    async with conexao() as conn:
        out = await _checkout(conn, uid, worker="w2", metodo="cartao")

    assert out["metodo"] == "cartao"
    assert out["invoice_url"] == "https://www.asaas.com/i/pay_card_novo"
    linhas = await _payments(uid)
    assert sorted((l["status"], l["metodo"]) for l in linhas) == [
        ("expirado", "pix"),
        ("pendente", "cartao"),
    ]


async def test_cobranca_antiga_paga_depois_ainda_concede_o_periodo(
    client, monkeypatch
):
    uid = await _criar_usuario(client, "r7c@x.com", "333.333.330-90")
    _asaas_com_ids_distintos(monkeypatch)

    async with conexao() as conn:
        primeiro = await _checkout(conn, uid)
    await _vencer_prazo_local(uid)
    async with conexao() as conn:
        await _checkout(conn, uid, worker="w2")

    # O usuário paga o PRIMEIRO PIX, que no Asaas continua valendo.
    async with conexao() as conn:
        async with conn.transaction():
            res = await billing.processar_webhook_asaas(
                conn,
                {
                    "event": "PAYMENT_CONFIRMED",
                    "payment": {
                        "id": "pay_pix_1",
                        "externalReference": primeiro["payment_id"],
                    },
                },
            )
    assert res["status"] == "confirmado"
    assert res["politica_b"] is True

    async with conexao() as conn:
        fim = await conn.fetchval(
            "SELECT periodo_fim > now() FROM subscriptions WHERE user_id = $1", uid
        )
    assert fim is True


async def test_http_checkout_no_dia_seguinte_nao_devolve_500(client, monkeypatch):
    uid = await _criar_usuario(client, "r7d@x.com", "313.313.313-66")
    _asaas_com_ids_distintos(monkeypatch)
    r = await client.post(
        "/api/v1/auth/login", json={"email": "r7d@x.com", "senha": "senha123"}
    )
    token = r.json()["token"]

    async def checkout_http(metodo):
        return await client.post(
            "/api/v1/billing/checkout",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={"plano": "pro_mensal", "metodo": metodo},
        )

    r1 = await checkout_http("pix")
    assert r1.status_code == 202, r1.text
    await _vencer_prazo_local(uid)

    r2 = await checkout_http("pix")
    assert r2.status_code == 202, r2.text
    assert r2.json()["payment_id"] != r1.json()["payment_id"]

    # No mesmo dia, clicar de novo devolve a MESMA cobrança nova.
    r3 = await checkout_http("pix")
    assert r3.status_code == 202, r3.text
    assert r3.json()["payment_id"] == r2.json()["payment_id"]


# ----------------------------------------------------------------
# GET /billing/status diz de onde vem o acesso (achado R8)
# ----------------------------------------------------------------

async def _status_http(client, email):
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "senha": "senha123"}
    )
    token = r.json()["token"]
    r = await client.get(
        "/api/v1/billing/status", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_status_informa_a_situacao_do_acesso(client):
    from datetime import datetime, timedelta, timezone

    uid = await _criar_usuario(client, "r8@x.com", "314.314.314-27")

    corpo = await _status_http(client, "r8@x.com")
    assert corpo["acesso"]["liberado"] is True
    assert corpo["acesso"]["situacao"] == "teste"
    teste_ate = datetime.fromisoformat(corpo["acesso"]["teste_ate"])
    falta = teste_ate - datetime.now(timezone.utc)
    assert timedelta(days=6, hours=23) < falta <= timedelta(days=7)

    async with conexao() as conn:
        await conn.execute(
            "UPDATE users SET criado_em = now() - interval '40 days' WHERE id = $1",
            uid,
        )
    corpo = await _status_http(client, "r8@x.com")
    assert corpo["acesso"] == {
        "liberado": False,
        "situacao": "trial_expirado",
        "teste_ate": corpo["acesso"]["teste_ate"],
    }
    assert corpo["subscription"] is None

    async with conexao() as conn:
        await conn.execute(
            "INSERT INTO subscriptions (user_id, plano, status, periodo_inicio, periodo_fim) "
            "VALUES ($1, 'pro_mensal', 'ativa', now() - interval '31 days', "
            "        now() - interval '1 day')",
            uid,
        )
    corpo = await _status_http(client, "r8@x.com")
    assert corpo["acesso"]["liberado"] is False
    assert corpo["acesso"]["situacao"] == "assinatura_expirada"
    # 'ativa' é o rótulo de "habilitada para renovação" (DECISOES 2026-09-26),
    # não de período vigente: quem decide o acesso é `acesso`.
    assert corpo["subscription"]["status"] == "ativa"

    async with conexao() as conn:
        await conn.execute(
            "UPDATE subscriptions SET periodo_fim = now() + interval '10 days' "
            " WHERE user_id = $1",
            uid,
        )
    corpo = await _status_http(client, "r8@x.com")
    assert corpo["acesso"]["liberado"] is True
    assert corpo["acesso"]["situacao"] == "assinatura"

    async with conexao() as conn:
        await conn.execute(
            "UPDATE users SET trial_exempt = TRUE WHERE id = $1", uid
        )
    corpo = await _status_http(client, "r8@x.com")
    assert corpo["acesso"]["situacao"] == "isento"
    assert corpo["acesso"]["liberado"] is True


async def test_status_e_lista_informam_plano_e_forma_do_pagamento(client, monkeypatch):
    """A tela precisa saber qual cobrança está esperando para reabri-la com a
    mesma forma de pagamento (achado R8)."""
    await _criar_usuario(client, "r8b@x.com", "315.315.315-98")
    _asaas_com_ids_distintos(monkeypatch)
    r = await client.post(
        "/api/v1/auth/login", json={"email": "r8b@x.com", "senha": "senha123"}
    )
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/billing/checkout",
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        json={"plano": "pro_anual", "metodo": "cartao"},
    )
    assert r.status_code == 202, r.text

    status = (await client.get("/api/v1/billing/status", headers=h)).json()
    assert status["ultimo_payment"]["plano"] == "pro_anual"
    assert status["ultimo_payment"]["metodo"] == "cartao"
    assert status["ultimo_payment"]["status"] == "pendente"

    itens = (await client.get("/api/v1/payments", headers=h)).json()["itens"]
    assert [(i["plano"], i["metodo"], i["status"]) for i in itens] == [
        ("pro_anual", "cartao", "pendente")
    ]
