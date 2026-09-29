"""Billing — checkout PIX via Asaas (M5).

Fluxo (CONTRATO_API.md § Billing):
  1. resolver/criar customer Asaas (users.asaas_customer_id)
  2. obter/criar payment local (external_reference = payments.id)
  3. adquirir claim persistente (exclusao mutua)
  4. GET Asaas por externalReference
     - encontrou -> adotar; vazio -> POST
  5. buscar e persistir QR code PIX
  6. liberar claim

Regra dura: nenhum POST de criacao no Asaas sem GET previo vazio.
Decimal obrigatorio na fronteira de valor.
"""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from ..security.audit import registrar_auditoria
from ..security.crypto import decifrar_cpf
from ..security.erros import erro
from . import asaas

# PENDENTE_CONFIRMACAO: precos e periodos dos planos nao estao no
# contrato ainda. Valores abaixo sao placeholder para destravar o M5.
_PLANOS: dict[str, tuple[Decimal, int]] = {
    "pro_mensal": (Decimal("49.90"), 30),
    "pro_anual": (Decimal("499.00"), 365),
}

_DUE_DATE_DIAS = 7


async def _resolver_customer(conn, user_id: UUID) -> str:
    """Retorna asaas_customer_id do usuario, criando se necessario.

    Ordem: local -> GET Asaas -> POST Asaas.
    """
    row = await conn.fetchrow(
        "SELECT asaas_customer_id, nome, email, cpf_cifrado "
        "  FROM users WHERE id = $1",
        user_id,
    )
    if row is None:
        raise erro(404, "USUARIO_NAO_ENCONTRADO", "Usuário não encontrado.")
    if row["asaas_customer_id"]:
        return row["asaas_customer_id"]

    cpf = decifrar_cpf(row["cpf_cifrado"])
    existente = await asaas.buscar_customer_por_cpf(cpf)
    if existente is not None:
        customer_id = existente["id"]
    else:
        criado = await asaas.criar_customer(
            nome=row["nome"] or "Cliente CaixaClaro",
            cpf=cpf,
            email=row["email"],
        )
        customer_id = criado["id"]

    await conn.execute(
        "UPDATE users SET asaas_customer_id = $1 WHERE id = $2",
        customer_id,
        user_id,
    )
    return customer_id


async def _obter_ou_criar_payment(conn, user_id, plano, valor, periodo_dias):
    """Retorna payment pendente reutilizavel ou cria novo.

    Reusa pendente do mesmo plano nao expirado para evitar acumular
    PIX nao pago. Retorna dict com id/status/asaas_payment_id/qrcode.
    """
    row = await conn.fetchrow(
        """
        SELECT id, status, asaas_payment_id, pix_qr_code, pix_copy_paste
          FROM payments
         WHERE user_id = $1 AND plano = $2 AND status = 'pendente'
           AND expira_em > now()
         ORDER BY criado_em DESC
         LIMIT 1
        """,
        user_id,
        plano,
    )
    if row is not None:
        return dict(row)

    novo = await conn.fetchrow(
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
    payment_id = novo["id"]
    await conn.execute(
        "UPDATE payments SET external_reference = $1 WHERE id = $2",
        str(payment_id),
        payment_id,
    )
    return {
        "id": payment_id,
        "status": "pendente",
        "asaas_payment_id": None,
        "pix_qr_code": None,
        "pix_copy_paste": None,
    }


async def _adquirir_claim(conn, payment_id, worker_id) -> bool:
    """UPDATE ... WHERE claimed_at IS NULL. Retorna True se ganhou."""
    row = await conn.fetchrow(
        """
        UPDATE payments
           SET claimed_at = now(),
               claimed_by = $1,
               tentativa_em = now()
         WHERE id = $2 AND claimed_at IS NULL
         RETURNING id
        """,
        worker_id,
        payment_id,
    )
    return row is not None


async def _liberar_claim(conn, payment_id) -> None:
    await conn.execute(
        "UPDATE payments SET claimed_at = NULL, claimed_by = NULL "
        " WHERE id = $1",
        payment_id,
    )


async def _adotar_ou_criar_asaas(customer_id, valor, plano, external_ref):
    """GET antes de POST. Devolve o payment do Asaas."""
    existente = await asaas.buscar_pagamento_por_external_reference(external_ref)
    if existente is not None:
        return existente
    due = (date.today() + timedelta(days=_DUE_DATE_DIAS)).isoformat()
    return await asaas.criar_pagamento_pix(
        customer_id=customer_id,
        valor=valor,
        external_reference=external_ref,
        descricao=f"CaixaClaro {plano}",
        due_date=due,
    )


async def checkout(conn, user_id, plano: str, worker_id: str) -> dict:
    """Executa o fluxo de checkout. Retorna dict com pix_qr_code/pix_copy_paste."""
    if plano not in _PLANOS:
        raise erro(400, "PLANO_INVALIDO", "Plano desconhecido.")
    valor, periodo_dias = _PLANOS[plano]

    # Serializa checkouts concorrentes do mesmo usuario. Requer transacao
    # ativa (chamado via executar_com_idempotencia, que envolve em
    # transacao). Sem isso, duas execucoes concorrentes podem criar dois
    # payments pendentes ou dois customers Asaas para o mesmo usuario.
    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext($1))",
        f"billing:{user_id}",
    )

    customer_id = await _resolver_customer(conn, user_id)

    payment = await _obter_ou_criar_payment(
        conn, user_id, plano, valor, periodo_dias
    )
    if payment["pix_qr_code"] and payment["pix_copy_paste"]:
        return {
            "payment_id": str(payment["id"]),
            "status": payment["status"],
            "pix_qr_code": payment["pix_qr_code"],
            "pix_copy_paste": payment["pix_copy_paste"],
        }

    ganhou = await _adquirir_claim(conn, payment["id"], worker_id)
    if not ganhou:
        raise erro(
            409,
            "CHECKOUT_EM_ANDAMENTO",
            "Checkout em andamento.",
            headers={"Retry-After": "1"},
        )

    try:
        external_ref = str(payment["id"])
        asaas_pay = await _adotar_ou_criar_asaas(
            customer_id, valor, plano, external_ref
        )
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
            payment["id"],
        )

        return {
            "payment_id": str(payment["id"]),
            "status": "pendente",
            "pix_qr_code": qr.get("encodedImage"),
            "pix_copy_paste": qr.get("payload"),
        }
    finally:
        await _liberar_claim(conn, payment["id"])


# ----------------------------------------------------------------
# Webhook Asaas (M5.7)
# ----------------------------------------------------------------

_EVENTOS_QUE_CONFIRMAM = {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}


async def _buscar_payment_duplo_lookup(conn, asaas_id, external_ref):
    """Duplo lookup: asaas_payment_id ou external_reference.

    Se ambos baterem em linhas diferentes, e' inconsistencia local
    e retornamos None (o webhook nao pode resolver sozinho).
    """
    if asaas_id:
        row = await conn.fetchrow(
            "SELECT id, user_id, plano, periodo_dias, status, "
            "       asaas_payment_id, external_reference "
            "  FROM payments WHERE asaas_payment_id = $1",
            asaas_id,
        )
        if row is not None:
            if external_ref and row["external_reference"] != external_ref:
                return None
            return row

    if external_ref:
        row = await conn.fetchrow(
            "SELECT id, user_id, plano, periodo_dias, status, "
            "       asaas_payment_id, external_reference "
            "  FROM payments WHERE external_reference = $1",
            external_ref,
        )
        if row is not None:
            if asaas_id and row["asaas_payment_id"] not in (None, asaas_id):
                return None
            return row

    return None


async def _conceder_periodo(conn, user_id, plano, periodo_dias, payment_id):
    """Cria ou estende a subscription do usuario.

    Semantica: subscription.status='ativa' = habilitada para renovacao
    (DECISOES 2026-09-26). Extensao parte de max(now, periodo_fim).
    """
    row = await conn.fetchrow(
        "SELECT id, periodo_fim FROM subscriptions WHERE user_id = $1",
        user_id,
    )
    if row is None:
        await conn.execute(
            """
            INSERT INTO subscriptions
              (user_id, plano, status, periodo_inicio, periodo_fim)
            VALUES ($1, $2, 'ativa', now(),
                    now() + make_interval(days => $3))
            """,
            user_id,
            plano,
            periodo_dias,
        )
    else:
        await conn.execute(
            """
            UPDATE subscriptions
               SET plano = $1,
                   status = 'ativa',
                   periodo_fim = GREATEST(now(), periodo_fim)
                                 + make_interval(days => $2),
                   atualizado_em = now()
             WHERE id = $3
            """,
            plano,
            periodo_dias,
            row["id"],
        )


async def _aplicar_payment_confirmed(conn, payment, payload):
    """Matriz PAYMENT_CONFIRMED × 5 estados locais.

    Retorna (novo_status, politica_b_aplicada).
    """
    atual = payment["status"]
    if atual == "confirmado":
        return "confirmado", False  # idempotente

    politica_b = atual == "expirado"

    if atual in ("pendente", "pendente_reconciliacao", "expirado", "falhou"):
        await conn.execute(
            """
            UPDATE payments
               SET status = 'confirmado',
                   atualizado_em = now()
             WHERE id = $1
            """,
            payment["id"],
        )
        await _conceder_periodo(
            conn,
            payment["user_id"],
            payment["plano"],
            payment["periodo_dias"],
            payment["id"],
        )
        return "confirmado", politica_b

    return atual, False


async def processar_webhook_asaas(conn, payload: dict) -> dict:
    """Processa evento do Asaas.

    Regra dura: user_id NUNCA vem do payload. Vem do payments local.
    """
    event = payload.get("event")
    payment_payload = payload.get("payment") or {}
    asaas_id = payment_payload.get("id")
    external_ref = payment_payload.get("externalReference")

    if not event or not asaas_id:
        raise erro(
            400,
            "WEBHOOK_PAYLOAD_INVALIDO",
            "event e payment.id obrigatórios.",
        )

    payment = await _buscar_payment_duplo_lookup(conn, asaas_id, external_ref)
    if payment is None:
        await registrar_auditoria(
            conn,
            ator="webhook_asaas",
            acao="WEBHOOK_ASAAS_PAYMENT_NAO_ENCONTRADO",
            alvo=asaas_id,
            meta={"event": event, "external_reference": external_ref},
        )
        return {"ok": True, "payment_encontrado": False}

    user_id = str(payment["user_id"])

    if event in _EVENTOS_QUE_CONFIRMAM:
        novo, politica_b = await _aplicar_payment_confirmed(conn, payment, payload)
        await registrar_auditoria(
            conn,
            ator="webhook_asaas",
            acao="PAYMENT_CONFIRMED_APLICADO",
            user_id=user_id,
            alvo=asaas_id,
            meta={
                "event": event,
                "payment_id": str(payment["id"]),
                "status_anterior": payment["status"],
                "status_novo": novo,
                "politica_b": politica_b,
                "periodo_dias": payment["periodo_dias"],
                "plano": payment["plano"],
            },
        )
        return {
            "ok": True,
            "payment_id": str(payment["id"]),
            "status": novo,
            "politica_b": politica_b,
        }

    if event == "PAYMENT_OVERDUE":
        if payment["status"] == "pendente":
            await conn.execute(
                "UPDATE payments SET status = 'expirado', atualizado_em = now() "
                " WHERE id = $1",
                payment["id"],
            )
        await registrar_auditoria(
            conn,
            ator="webhook_asaas",
            acao="PAYMENT_OVERDUE_APLICADO",
            user_id=user_id,
            alvo=asaas_id,
            meta={"payment_id": str(payment["id"])},
        )
        return {"ok": True, "payment_id": str(payment["id"]), "status": "expirado"}

    if event == "PAYMENT_DELETED":
        if payment["status"] == "pendente":
            await conn.execute(
                "UPDATE payments SET status = 'falhou', atualizado_em = now() "
                " WHERE id = $1",
                payment["id"],
            )
        await registrar_auditoria(
            conn,
            ator="webhook_asaas",
            acao="PAYMENT_DELETED_APLICADO",
            user_id=user_id,
            alvo=asaas_id,
            meta={"payment_id": str(payment["id"])},
        )
        return {"ok": True, "payment_id": str(payment["id"]), "status": "falhou"}

    await registrar_auditoria(
        conn,
        ator="webhook_asaas",
        acao="WEBHOOK_ASAAS_EVENTO_IGNORADO",
        user_id=user_id,
        alvo=asaas_id,
        meta={"event": event},
    )
    return {"ok": True, "ignorado": event}



