"""Testes do client Asaas — M5.

Cobrem:
  - sem credenciais -> 503 ASAAS_NAO_CONFIGURADO
  - buscar_customer_por_cpf: 200 com 1 resultado / 200 vazio / 500 -> 502
  - criar_customer: 201 + header access_token + payload
  - buscar_pagamento_por_external_reference: 200 com 1 / vazio
  - criar_pagamento_pix: 200 + payload exato
  - buscar_pix_qrcode: 200

Sem I/O real: httpx.AsyncClient e substituido por MockTransport.
"""
import json
from decimal import Decimal

import httpx
import pytest
from fastapi import HTTPException

from caixaclaro.config import settings
from caixaclaro.services import asaas as asaas_mod


def _com_credenciais(monkeypatch):
    s = settings()
    monkeypatch.setattr(s, "asaas_api_key", "asaas-key")
    monkeypatch.setattr(s, "asaas_base_url", "https://api.asaas.com/v3")


def _sem_credenciais(monkeypatch):
    s = settings()
    monkeypatch.setattr(s, "asaas_api_key", None)


def _mock_transport(handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    return factory


async def test_sem_credenciais_erro_503(monkeypatch):
    _sem_credenciais(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await asaas_mod.buscar_customer_por_cpf("11111111111")
    assert exc.value.status_code == 503
    assert exc.value.detail["erro"] == "ASAAS_NAO_CONFIGURADO"


async def test_buscar_customer_por_cpf_encontrado(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/v3/customers":
            assert request.method == "GET"
            assert request.headers["access_token"] == "asaas-key"
            assert request.url.params["cpfCnpj"] == "11111111111"
            return httpx.Response(
                200,
                json={"data": [{"id": "cus_1", "cpfCnpj": "11111111111"}]},
            )
        return httpx.Response(404)

    monkeypatch.setattr(asaas_mod.httpx, "AsyncClient", _mock_transport(handler))
    out = await asaas_mod.buscar_customer_por_cpf("11111111111")
    assert out == {"id": "cus_1", "cpfCnpj": "11111111111"}


async def test_buscar_customer_por_cpf_vazio(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(asaas_mod.httpx, "AsyncClient", _mock_transport(handler))
    out = await asaas_mod.buscar_customer_por_cpf("99999999999")
    assert out is None


async def test_buscar_customer_por_cpf_falha_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        return httpx.Response(500)

    monkeypatch.setattr(asaas_mod.httpx, "AsyncClient", _mock_transport(handler))
    with pytest.raises(HTTPException) as exc:
        await asaas_mod.buscar_customer_por_cpf("11111111111")
    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "ASAAS_CUSTOMER_BUSCAR_FALHOU"


async def test_criar_customer(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        if request.url.path == "/v3/customers":
            assert request.method == "POST"
            assert request.headers["access_token"] == "asaas-key"
            body = json.loads(request.content)
            assert body == {
                "name": "Maria Silva",
                "cpfCnpj": "11111111111",
                "email": "m@x.com",
            }
            return httpx.Response(201, json={"id": "cus_2"})
        return httpx.Response(404)

    monkeypatch.setattr(asaas_mod.httpx, "AsyncClient", _mock_transport(handler))
    out = await asaas_mod.criar_customer("Maria Silva", "11111111111", "m@x.com")
    assert out == {"id": "cus_2"}


async def test_criar_customer_falha_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        return httpx.Response(400, json={"errors": [{"description": "CPF invalido"}]})

    monkeypatch.setattr(asaas_mod.httpx, "AsyncClient", _mock_transport(handler))
    with pytest.raises(HTTPException) as exc:
        await asaas_mod.criar_customer("X", "X", "x@x.com")
    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "ASAAS_CUSTOMER_CRIAR_FALHOU"


async def test_buscar_pagamento_por_external_reference(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v3/payments"
        assert request.url.params["externalReference"] == "pay-local-1"
        assert request.headers["access_token"] == "asaas-key"
        return httpx.Response(
            200,
            json={"data": [{"id": "pay_1", "externalReference": "pay-local-1"}]},
        )

    monkeypatch.setattr(asaas_mod.httpx, "AsyncClient", _mock_transport(handler))
    out = await asaas_mod.buscar_pagamento_por_external_reference("pay-local-1")
    assert out == {"id": "pay_1", "externalReference": "pay-local-1"}


async def test_buscar_pagamento_vazio_retorna_none(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(asaas_mod.httpx, "AsyncClient", _mock_transport(handler))
    out = await asaas_mod.buscar_pagamento_por_external_reference("pay-local-1")
    assert out is None


async def test_criar_pagamento_pix(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v3/payments"
        assert request.method == "POST"
        body = json.loads(request.content)
        assert body == {
            "customer": "cus_1",
            "billingType": "PIX",
            "value": 49.9,
            "dueDate": "2026-10-15",
            "description": "CaixaClaro pro_mensal",
            "externalReference": "pay-local-1",
        }
        return httpx.Response(
            200,
            json={
                "id": "pay_1",
                "status": "PENDING",
                "externalReference": "pay-local-1",
            },
        )

    monkeypatch.setattr(asaas_mod.httpx, "AsyncClient", _mock_transport(handler))
    out = await asaas_mod.criar_pagamento_pix(
        customer_id="cus_1",
        valor=Decimal("49.90"),
        external_reference="pay-local-1",
        descricao="CaixaClaro pro_mensal",
        due_date="2026-10-15",
    )
    assert out["id"] == "pay_1"
    assert out["externalReference"] == "pay-local-1"


async def test_buscar_pix_qrcode(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v3/payments/pay_1/pixQrCode"
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "encodedImage": "base64...",
                "payload": "000201263...",
                "expirationDate": "2026-10-15",
            },
        )

    monkeypatch.setattr(asaas_mod.httpx, "AsyncClient", _mock_transport(handler))
    out = await asaas_mod.buscar_pix_qrcode("pay_1")
    assert out["payload"] == "000201263..."
    assert "encodedImage" in out




async def test_criar_pagamento_cartao_avulso(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v3/payments"
        assert request.method == "POST"

        body = json.loads(request.content)

        assert body == {
            "customer": "cus_1",
            "billingType": "CREDIT_CARD",
            "value": 29.9,
            "dueDate": "2026-10-15",
            "description": "CaixaClaro pro_mensal",
            "externalReference": "pay-local-card-1",
            "callback": {"successUrl": "https://app.example.com"},
        }

        assert "creditCard" not in body
        assert "creditCardHolderInfo" not in body
        assert "installmentCount" not in body

        return httpx.Response(
            200,
            json={
                "id": "pay_card_1",
                "status": "PENDING",
                "externalReference": "pay-local-card-1",
                "invoiceUrl": "https://www.asaas.com/i/pay_card_1",
            },
        )

    monkeypatch.setattr(
        asaas_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    out = await asaas_mod.criar_pagamento_cartao_avulso(
        customer_id="cus_1",
        valor=Decimal("29.90"),
        external_reference="pay-local-card-1",
        descricao="CaixaClaro pro_mensal",
        due_date="2026-10-15",
        success_url="https://app.example.com",
    )

    assert out["id"] == "pay_card_1"
    assert out["status"] == "PENDING"
    assert out["externalReference"] == "pay-local-card-1"
    assert out["invoiceUrl"] == "https://www.asaas.com/i/pay_card_1"


async def test_criar_pagamento_cartao_avulso_falha_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v3/payments"
        assert request.method == "POST"
        return httpx.Response(
            400,
            json={"errors": [{"description": "Falha no payment"}]},
        )

    monkeypatch.setattr(
        asaas_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    with pytest.raises(HTTPException) as exc:
        await asaas_mod.criar_pagamento_cartao_avulso(
            customer_id="cus_1",
            valor=Decimal("29.90"),
            external_reference="pay-local-card-1",
            descricao="CaixaClaro pro_mensal",
            due_date="2026-10-15",
            success_url="https://app.example.com",
        )

    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "ASAAS_PAYMENT_CRIAR_FALHOU"


async def test_buscar_pagamento_por_id(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v3/payments/pay_card_1"
        assert request.method == "GET"
        assert request.headers["access_token"] == "asaas-key"

        return httpx.Response(
            200,
            json={
                "id": "pay_card_1",
                "status": "PENDING",
                "externalReference": "pay-local-card-1",
            },
        )

    monkeypatch.setattr(
        asaas_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    out = await asaas_mod.buscar_pagamento_por_id("pay_card_1")

    assert out == {
        "id": "pay_card_1",
        "status": "PENDING",
        "externalReference": "pay-local-card-1",
    }


async def test_buscar_pagamento_por_id_404_retorna_none(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v3/payments/pay_inexistente"
        assert request.method == "GET"
        return httpx.Response(404)

    monkeypatch.setattr(
        asaas_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    out = await asaas_mod.buscar_pagamento_por_id("pay_inexistente")

    assert out is None


async def test_cancelar_pagamento(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v3/payments/pay_card_1"
        assert request.method == "DELETE"
        assert request.headers["access_token"] == "asaas-key"
        return httpx.Response(200)

    monkeypatch.setattr(
        asaas_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    out = await asaas_mod.cancelar_pagamento("pay_card_1")

    assert out is None


async def test_cancelar_pagamento_falha_502(monkeypatch):
    _com_credenciais(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v3/payments/pay_card_1"
        assert request.method == "DELETE"
        return httpx.Response(
            400,
            json={"errors": [{"description": "Payment nao pode ser removido"}]},
        )

    monkeypatch.setattr(
        asaas_mod.httpx,
        "AsyncClient",
        _mock_transport(handler),
    )

    with pytest.raises(HTTPException) as exc:
        await asaas_mod.cancelar_pagamento("pay_card_1")

    assert exc.value.status_code == 502
    assert exc.value.detail["erro"] == "ASAAS_PAYMENT_CANCELAR_FALHOU"

async def test_criar_pagamento_cartao_avulso_sem_callback(monkeypatch):
    """Rota 2: success_url=None nao envia callback ao Asaas."""
    _com_credenciais(monkeypatch)
    capturado = {}

    def handler(request):
        capturado["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"id": "pay_card_sem_cb", "invoiceUrl": "https://x/i/y"},
        )

    monkeypatch.setattr(
        asaas_mod.httpx, "AsyncClient", _mock_transport(handler)
    )

    out = await asaas_mod.criar_pagamento_cartao_avulso(
        customer_id="cus_1",
        valor=Decimal("29.90"),
        external_reference="ref_1",
        descricao="CaixaClaro pro_mensal",
        due_date="2026-10-10",
        success_url=None,
    )

    assert out["invoiceUrl"] == "https://x/i/y"
    assert "callback" not in capturado["body"]