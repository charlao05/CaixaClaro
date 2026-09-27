"""Renewal — renovacao automatica de assinaturas (M6.3).

Contrato: docs/CONTRATOS_INTERNOS.md §12.
"""
from datetime import date, datetime, timedelta

import httpx

from ..security.audit import registrar_auditoria
from . import asaas, billing

_DUE_DATE_DIAS = 7


def _so_data(v):
    """Normaliza TIMESTAMPTZ->date. asyncpg devolve datetime em TIMESTAMPTZ."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    return v


async def _deve_cobrar(sub) -> bool:
    """Aplica as 3 regras de skip de §12 antes do check de pendente."""
    if sub["status"] != "ativa":
        return False
    pausada = _so_data(sub["pausada_ate"])
    if pausada is not None and pausada >= date.today():
        return False
    fim = _so_data(sub["periodo_fim"])
    if fim is None:
        return False
    if fim > date.today() + timedelta(days=3):
        return False
    return True


async def _tem_pendente_vigente(conn, user_id, plano) -> bool:
    row = await conn.fetchval(
        """
        SELECT 1 FROM payments
         WHERE user_id = $1 AND plano = $2
           AND status = 'pendente'
           AND expira_em > now()
         LIMIT 1
        """,
        user_id,
        plano,
    )
    return row is not None


async def _criar_cobranca(conn, user_id, plano, worker_id):
    """Cria payment novo, adquire claim, GET-antes-de-POST e persiste."""
    customer_id = await billing._resolver_customer(conn, user_id)
    valor, periodo_dias = billing._PLANOS[plano]

    # §12 item 3: pendente expirado nao bloqueia nova cobranca. Marca o
    # antigo como 'expirado' antes de inserir — assim o UNIQUE parcial
    # payments_pendente_uq nao barra o novo pagamento.
    await conn.execute(
        """
        UPDATE payments
           SET status = 'expirado',
               atualizado_em = now()
         WHERE user_id = $1 AND plano = $2
           AND status = 'pendente'
           AND expira_em <= now()
        """,
        user_id,
        plano,
    )

    row = await conn.fetchrow(
        """
        INSERT INTO payments (user_id, plano, valor, periodo_dias, status)
        VALUES ($1, $2, $3, $4, 'pendente')
        RETURNING id
        """,
        user_id,
        plano,
        valor,
        periodo_dias,
    )
    payment_id = row["id"]
    external_ref = str(payment_id)
    await conn.execute(
        "UPDATE payments SET external_reference = $1 WHERE id = $2",
        external_ref,
        payment_id,
    )

    ganhou = await billing._adquirir_claim(conn, payment_id, worker_id)
    if not ganhou:
        return None

    try:
        existente = await asaas.buscar_pagamento_por_external_reference(external_ref)
        if existente is not None:
            asaas_pay = existente
        else:
            due = (date.today() + timedelta(days=_DUE_DATE_DIAS)).isoformat()
            try:
                asaas_pay = await asaas.criar_pagamento_pix(
                    customer_id=customer_id,
                    valor=valor,
                    external_reference=external_ref,
                    descricao=f"CaixaClaro {plano}",
                    due_date=due,
                )
            except httpx.HTTPError:
                await conn.execute(
                    """
                    UPDATE payments
                       SET status = 'pendente_reconciliacao',
                           atualizado_em = now()
                     WHERE id = $1
                    """,
                    payment_id,
                )
                raise

        qr = await asaas.buscar_pix_qrcode(asaas_pay["id"])
        await conn.execute(
            """
            UPDATE payments
               SET asaas_payment_id = $1,
                   pix_qr_code = $2,
                   pix_copy_paste = $3,
                   atualizado_em = now()
             WHERE id = $4
            """,
            asaas_pay["id"],
            qr.get("encodedImage"),
            qr.get("payload"),
            payment_id,
        )
        await registrar_auditoria(
            conn,
            ator="worker",
            acao="RENEWAL_COBRANCA_CRIADA",
            user_id=str(user_id),
            alvo=str(payment_id),
            meta={"plano": plano, "valor": str(valor)},
        )
    finally:
        await billing._liberar_claim(conn, payment_id)

    return payment_id


async def renovar_uma(conn, sub_id, worker_id) -> dict:
    """Processa uma subscription. Nao levanta para skip; propaga HTTPError."""
    sub = await conn.fetchrow(
        """
        SELECT id, user_id, plano, status, periodo_fim, pausada_ate
          FROM subscriptions
         WHERE id = $1
        """,
        sub_id,
    )
    if sub is None:
        return {"status": "not_found"}

    if not await _deve_cobrar(sub):
        return {"status": "skip", "motivo": "regras_skip"}

    if await _tem_pendente_vigente(conn, sub["user_id"], sub["plano"]):
        return {"status": "skip", "motivo": "pendente_vigente"}

    try:
        payment_id = await _criar_cobranca(
            conn, sub["user_id"], sub["plano"], worker_id
        )
    except Exception as e:
        if "payments_pendente_uq" in str(e):
            return {"status": "skip", "motivo": "corrida_pendente"}
        raise

    if payment_id is None:
        return {"status": "claim_perdido"}
    return {"status": "cobrado", "payment_id": str(payment_id)}


async def renovar_assinaturas(conn, worker_id) -> dict:
    """Varre subscriptions vencidas e processa cada uma."""
    rows = await conn.fetch(
        """
        SELECT id FROM subscriptions
         WHERE status = 'ativa'
           AND periodo_fim IS NOT NULL
           AND periodo_fim <= ($1::date + interval '3 days')
         ORDER BY periodo_fim
        """,
        date.today(),
    )
    stats = {
        "total": len(rows),
        "cobrados": 0,
        "skip": 0,
        "claim_perdido": 0,
        "not_found": 0,
        "reconciliacao": 0,
    }
    for row in rows:
        try:
            r = await renovar_uma(conn, row["id"], worker_id)
        except httpx.HTTPError:
            stats["reconciliacao"] += 1
            continue
        s = r["status"]
        if s == "cobrado":
            stats["cobrados"] += 1
        elif s == "claim_perdido":
            stats["claim_perdido"] += 1
        elif s == "not_found":
            stats["not_found"] += 1
        else:
            stats["skip"] += 1
    return stats
