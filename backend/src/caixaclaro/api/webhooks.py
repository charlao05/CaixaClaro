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
