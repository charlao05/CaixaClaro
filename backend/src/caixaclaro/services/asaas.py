"""Cliente Asaas — M5 (billing).

Escopo minimo: customer (buscar/criar), payment (buscar por
externalReference / criar PIX) e QR code PIX.
Sem retry, sem cache.

Contrato: docs/CONTRATO_API.md secao "Billing".
"""
import logging
from decimal import Decimal

import httpx

from ..config import settings
from ..security.erros import erro

logger = logging.getLogger(__name__)


def _config() -> tuple[str, str]:
    s = settings()
    if not s.asaas_api_key:
        raise erro(
            503,
            "ASAAS_NAO_CONFIGURADO",
            "Credenciais Asaas ausentes no ambiente.",
        )
    return s.asaas_api_key, s.asaas_base_url


def _headers(api_key: str) -> dict:
    return {"access_token": api_key, "Content-Type": "application/json"}


async def buscar_customer_por_cpf(cpf: str) -> dict | None:
    """GET /customers?cpfCnpj={cpf}. Retorna o primeiro ou None."""
    api_key, base = _config()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.get(
            "/customers",
            params={"cpfCnpj": cpf},
            headers=_headers(api_key),
        )
        if r.status_code != 200:
            logger.warning(
                "asaas_customer_buscar_falhou",
                extra={
                    "asaas_status": r.status_code,
                    "asaas_method": "GET",
                    "asaas_path": "/customers",
                    "asaas_body_preview": r.content.decode("utf-8", errors="replace")[:500],
                },
            )
            raise erro(
                502,
                "ASAAS_CUSTOMER_BUSCAR_FALHOU",
                "Falha ao buscar customer no Asaas.",
            )
        data = r.json().get("data") or []
        return data[0] if data else None


async def criar_customer(nome: str, cpf: str, email: str) -> dict:
    """POST /customers. Retorna o customer criado."""
    api_key, base = _config()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.post(
            "/customers",
            headers=_headers(api_key),
            json={"name": nome, "cpfCnpj": cpf, "email": email},
        )
        if r.status_code not in (200, 201):
            logger.warning(
                "asaas_customer_criar_falhou",
                extra={
                    "asaas_status": r.status_code,
                    "asaas_method": "POST",
                    "asaas_path": "/customers",
                    "asaas_body_preview": r.content.decode("utf-8", errors="replace")[:500],
                },
            )
            raise erro(
                502,
                "ASAAS_CUSTOMER_CRIAR_FALHOU",
                "Falha ao criar customer no Asaas.",
            )
        return r.json()


async def buscar_pagamento_por_external_reference(ref: str) -> dict | None:
    """GET /payments?externalReference={ref}. Retorna o primeiro ou None."""
    api_key, base = _config()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.get(
            "/payments",
            params={"externalReference": ref},
            headers=_headers(api_key),
        )
        if r.status_code != 200:
            logger.warning(
                "asaas_payment_buscar_falhou",
                extra={
                    "asaas_status": r.status_code,
                    "asaas_method": "GET",
                    "asaas_path": "/payments",
                    "asaas_body_preview": r.content.decode("utf-8", errors="replace")[:500],
                },
            )
            raise erro(
                502,
                "ASAAS_PAYMENT_BUSCAR_FALHOU",
                "Falha ao buscar payment no Asaas.",
            )
        data = r.json().get("data") or []
        return data[0] if data else None


def _valor_json(valor: Decimal) -> float:
    """Serializa Decimal para numero JSON.

    O dominio usa Decimal; a API Asaas espera numero JSON. Quantizamos
    para 2 casas antes de converter, para o JSON sair como 49.9/49.99
    em vez de 49.899999999996.
    """
    return float(valor.quantize(Decimal("0.01")))

async def _criar_pagamento(
    billing_type: str,
    customer_id: str,
    valor: Decimal,
    external_reference: str,
    descricao: str,
    due_date: str,
) -> dict:
    """POST /payments com o instrumento informado."""
    api_key, base = _config()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.post(
            "/payments",
            headers=_headers(api_key),
            json={
                "customer": customer_id,
                "billingType": billing_type,
                "value": _valor_json(valor),
                "dueDate": due_date,
                "description": descricao,
                "externalReference": external_reference,
            },
        )
        if r.status_code not in (200, 201):
            logger.warning(
                "asaas_payment_criar_falhou",
                extra={
                    "asaas_status": r.status_code,
                    "asaas_method": "POST",
                    "asaas_path": "/payments",
                    "asaas_body_preview": r.content.decode("utf-8", errors="replace")[:500],
                },
            )
            raise erro(
                502,
                "ASAAS_PAYMENT_CRIAR_FALHOU",
                "Falha ao criar payment no Asaas.",
            )
        return r.json()


async def criar_pagamento_pix(
    customer_id: str,
    valor: Decimal,
    external_reference: str,
    descricao: str,
    due_date: str,
) -> dict:
    """POST /payments com billingType=PIX."""
    return await _criar_pagamento(
        billing_type="PIX",
        customer_id=customer_id,
        valor=valor,
        external_reference=external_reference,
        descricao=descricao,
        due_date=due_date,
    )


async def criar_pagamento_cartao_avulso(
    customer_id: str,
    valor: Decimal,
    external_reference: str,
    descricao: str,
    due_date: str,
) -> dict:
    """POST /payments com billingType=CREDIT_CARD.

    O cartao e processado pela Invoice hospedada do Asaas.
    Nenhum dado de cartao entra no CaixaClaro.
    """
    return await _criar_pagamento(
        billing_type="CREDIT_CARD",
        customer_id=customer_id,
        valor=valor,
        external_reference=external_reference,
        descricao=descricao,
        due_date=due_date,
    )


async def buscar_pagamento_por_id(payment_id: str) -> dict | None:
    """GET /payments/{id}. Retorna None quando o payment nao existe."""
    api_key, base = _config()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.get(
            f"/payments/{payment_id}",
            headers=_headers(api_key),
        )

        if r.status_code == 404:
            return None

        if r.status_code != 200:
            logger.warning(
                "asaas_payment_buscar_por_id_falhou",
                extra={
                    "asaas_status": r.status_code,
                    "asaas_method": "GET",
                    "asaas_path": "/payments/{id}",
                    "asaas_body_preview": r.content.decode("utf-8", errors="replace")[:500],
                },
            )
            raise erro(
                502,
                "ASAAS_PAYMENT_BUSCAR_FALHOU",
                "Falha ao buscar payment no Asaas.",
            )

        return r.json()


async def cancelar_pagamento(payment_id: str) -> None:
    """DELETE /payments/{id}."""
    api_key, base = _config()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.delete(
            f"/payments/{payment_id}",
            headers=_headers(api_key),
        )

        if r.status_code not in (200, 204):
            logger.warning(
                "asaas_payment_cancelar_falhou",
                extra={
                    "asaas_status": r.status_code,
                    "asaas_method": "DELETE",
                    "asaas_path": "/payments/{id}",
                    "asaas_body_preview": r.content.decode("utf-8", errors="replace")[:500],
                },
            )
            raise erro(
                502,
                "ASAAS_PAYMENT_CANCELAR_FALHOU",
                "Falha ao cancelar payment no Asaas.",
            )


async def buscar_pix_qrcode(payment_id: str) -> dict:
    """GET /payments/{id}/pixQrCode. Retorna encodedImage e payload."""
    api_key, base = _config()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.get(
            f"/payments/{payment_id}/pixQrCode",
            headers=_headers(api_key),
        )
        if r.status_code != 200:
            logger.warning(
                "asaas_pix_qr_falhou",
                extra={
                    "asaas_status": r.status_code,
                    "asaas_method": "GET",
                    "asaas_path": "/payments/{id}/pixQrCode",
                    "asaas_body_preview": r.content.decode("utf-8", errors="replace")[:500],
                },
            )
            raise erro(
                502,
                "ASAAS_PIX_QR_FALHOU",
                "Falha ao buscar QR code PIX no Asaas.",
            )
        return r.json()

