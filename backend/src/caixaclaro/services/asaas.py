"""Cliente Asaas — M5 (billing).

Escopo minimo: customer (buscar/criar), payment (buscar por
externalReference / criar PIX) e QR code PIX.
Sem retry, sem cache.

Contrato: docs/CONTRATO_API.md secao "Billing".
"""
import httpx

from ..config import settings
from ..security.erros import erro


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
            raise erro(
                502,
                "ASAAS_PAYMENT_BUSCAR_FALHOU",
                "Falha ao buscar payment no Asaas.",
            )
        data = r.json().get("data") or []
        return data[0] if data else None


async def criar_pagamento_pix(
    customer_id: str,
    valor: float,
    external_reference: str,
    descricao: str,
    due_date: str,
) -> dict:
    """POST /payments com billingType=PIX. Retorna o payment criado."""
    api_key, base = _config()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.post(
            "/payments",
            headers=_headers(api_key),
            json={
                "customer": customer_id,
                "billingType": "PIX",
                "value": valor,
                "dueDate": due_date,
                "description": descricao,
                "externalReference": external_reference,
            },
        )
        if r.status_code not in (200, 201):
            raise erro(
                502,
                "ASAAS_PAYMENT_CRIAR_FALHOU",
                "Falha ao criar payment no Asaas.",
            )
        return r.json()


async def buscar_pix_qrcode(payment_id: str) -> dict:
    """GET /payments/{id}/pixQrCode. Retorna encodedImage e payload."""
    api_key, base = _config()
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.get(
            f"/payments/{payment_id}/pixQrCode",
            headers=_headers(api_key),
        )
        if r.status_code != 200:
            raise erro(
                502,
                "ASAAS_PIX_QR_FALHOU",
                "Falha ao buscar QR code PIX no Asaas.",
            )
        return r.json()
