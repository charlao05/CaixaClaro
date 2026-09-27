"""Webhooks externos (M3b).

Hoje: POST /webhooks/pluggy processando item/created.
Idempotencia por UNIQUE(origem, event_id); processamento e insercao do
evento ocorrem na MESMA transacao, para que falha do handler reverta o
registro do evento e o retry da Pluggy efetivamente reprocesse.
"""
import json

from fastapi import APIRouter, Request

from ..db import conexao
from ..security.erros import erro
from ..services.contas import processar_item_created
from ..services.billing import processar_webhook_asaas
from ..services import telegram_bot
from ..services.telegram import vincular_por_token

router = APIRouter()


@router.post("/pluggy")
async def webhook_pluggy(request: Request):
    payload = await request.json()
    event = payload.get("event")
    event_id = payload.get("eventId") or payload.get("id")
    if not event or not event_id:
        raise erro(
            400,
            "WEBHOOK_PAYLOAD_INVALIDO",
            "event e eventId obrigatorios.",
        )

    async with conexao() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO webhook_events (origem, event_id, payload)
                VALUES ('pluggy', $1, $2::jsonb)
                ON CONFLICT (origem, event_id) DO NOTHING
                RETURNING id
                """,
                str(event_id),
                json.dumps(payload, ensure_ascii=False),
            )
            if row is None:
                return {"ok": True, "duplicado": True}

            if event == "item/created":
                resultado = await processar_item_created(conn, payload)
                return {"ok": True, "processado": resultado}

            return {"ok": True, "ignorado": event}

@router.post("/asaas")
async def webhook_asaas(request: Request):
    payload = await request.json()
    event = payload.get("event")
    event_id = payload.get("eventId") or payload.get("id")

    if not event or not event_id:
        raise erro(
            400,
            "WEBHOOK_PAYLOAD_INVALIDO",
            "event e eventId obrigatorios.",
        )

    async with conexao() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO webhook_events (origem, event_id, payload)
                VALUES ('asaas', $1, $2::jsonb)
                ON CONFLICT (origem, event_id) DO NOTHING
                RETURNING id
                """,
                str(event_id),
                json.dumps(payload, ensure_ascii=False),
            )

            if row is None:
                return {"ok": True, "duplicado": True}

            return await processar_webhook_asaas(conn, payload)


@router.post("/telegram")
async def webhook_telegram(request: Request):
    """Recebe update do Telegram. Unico fluxo que grava telegram_chat_id.

    Vinculacao ocorre quando chega mensagem /start <token>. Outros
    updates sao registrados mas ignorados.
    """
    payload = await request.json()
    update_id = payload.get("update_id")
    if update_id is None:
        raise erro(
            400,
            "WEBHOOK_PAYLOAD_INVALIDO",
            "update_id obrigatorio.",
        )

    message = payload.get("message") or {}
    text = message.get("text") or ""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    vinculado_para: dict | None = None

    async with conexao() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO webhook_events (origem, event_id, payload)
                VALUES ('telegram', $1, $2::jsonb)
                ON CONFLICT (origem, event_id) DO NOTHING
                RETURNING id
                """,
                str(update_id),
                json.dumps(payload, ensure_ascii=False),
            )
            if row is None:
                return {"ok": True, "duplicado": True}

            if not chat_id or not text.startswith("/start"):
                return {"ok": True, "ignorado": True}

            partes = text.split(maxsplit=1)
            if len(partes) < 2:
                return {"ok": True, "ignorado": "sem_token"}

            token = partes[1].strip()
            vinculado_para = await vincular_por_token(
                conn, token, int(chat_id)
            )

    # Envio fora da transacao: falha no Telegram nao desfaz a vinculacao.
    try:
        await telegram_bot.enviar_mensagem(
            int(chat_id),
            "CaixaClaro vinculado com sucesso. "
            "Voce vai receber aqui alertas de faturamento e DAS.",
        )
    except Exception as e:
        print(f"[webhook_telegram] falha ao enviar boas-vindas: {e}")

    return {"ok": True, "vinculado": vinculado_para}
