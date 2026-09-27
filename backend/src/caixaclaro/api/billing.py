"""Billing HTTP (M5).

Endpoints:
  POST /billing/checkout  (Idempotency-Key obrigatorio)
  POST /billing/pausar
  GET  /billing/status
  GET  /payments
"""
from datetime import date

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ..api.deps import usuario
from ..db import conexao
from ..security.erros import erro
from ..security.idempotency import executar_com_idempotencia
from ..services import billing

router = APIRouter()
payments_router = APIRouter()


class CheckoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plano: str


class PausarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pausada_ate: date | None = None


@router.post("/checkout")
async def checkout(
    body: CheckoutIn,
    u: dict = Depends(usuario),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    async def operacao(conn):
        result = await billing.checkout(
            conn, u["id"], body.plano, worker_id=idempotency_key
        )
        return result, 202

    resposta, status = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota="POST /billing/checkout",
        chave=idempotency_key,
        body={"plano": body.plano},
        operacao=operacao,
    )
    return JSONResponse(status_code=status, content=resposta)


@router.post("/pausar")
async def pausar(body: PausarIn, u: dict = Depends(usuario)):
    async with conexao() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM subscriptions WHERE user_id = $1", u["id"]
        )
        if row is None:
            raise erro(
                404,
                "SUBSCRIPTION_NAO_ENCONTRADA",
                "Sem assinatura para pausar.",
            )
        await conn.execute(
            """
            UPDATE subscriptions
               SET status = 'pausada',
                   pausada_ate = $1,
                   atualizado_em = now()
             WHERE id = $2
            """,
            body.pausada_ate,
            row["id"],
        )
    return {
        "ok": True,
        "status": "pausada",
        "pausada_ate": body.pausada_ate.isoformat() if body.pausada_ate else None,
    }


@router.get("/status")
async def status(u: dict = Depends(usuario)):
    async with conexao() as conn:
        sub = await conn.fetchrow(
            "SELECT plano, status, periodo_inicio, periodo_fim, pausada_ate "
            "  FROM subscriptions WHERE user_id = $1",
            u["id"],
        )
        pag = await conn.fetchrow(
            "SELECT id, status, pix_qr_code, criado_em "
            "  FROM payments WHERE user_id = $1 "
            " ORDER BY criado_em DESC LIMIT 1",
            u["id"],
        )
    return {
        "subscription": None
        if sub is None
        else {
            "plano": sub["plano"],
            "status": sub["status"],
            "periodo_inicio": (
                sub["periodo_inicio"].isoformat() if sub["periodo_inicio"] else None
            ),
            "periodo_fim": (
                sub["periodo_fim"].isoformat() if sub["periodo_fim"] else None
            ),
            "pausada_ate": (
                sub["pausada_ate"].isoformat() if sub["pausada_ate"] else None
            ),
        },
        "ultimo_payment": None
        if pag is None
        else {
            "id": str(pag["id"]),
            "status": pag["status"],
            "tem_qr": pag["pix_qr_code"] is not None,
            "criado_em": pag["criado_em"].isoformat(),
        },
    }


@payments_router.get("")
async def listar_payments(u: dict = Depends(usuario)):
    async with conexao() as conn:
        rows = await conn.fetch(
            """
            SELECT id, plano, valor, periodo_dias, status,
                   asaas_payment_id, criado_em
              FROM payments
             WHERE user_id = $1
             ORDER BY criado_em DESC, id DESC
            """,
            u["id"],
        )
    return {
        "itens": [
            {
                "id": str(r["id"]),
                "plano": r["plano"],
                "valor": str(r["valor"]),
                "periodo_dias": r["periodo_dias"],
                "status": r["status"],
                "asaas_payment_id": r["asaas_payment_id"],
                "criado_em": r["criado_em"].isoformat(),
            }
            for r in rows
        ]
    }

