"""Endpoint de vinculacao Telegram (M7).

Escopo: geracao de token. A vinculacao em si acontece via
POST /webhooks/telegram (unico fluxo que grava telegram_chat_id).
"""
from fastapi import APIRouter, Depends

from ..api.deps import usuario
from ..db import conexao
from ..services.telegram import gerar_token_vinculacao

router = APIRouter()


@router.post("/token-vinculacao")
async def token_vinculacao(u: dict = Depends(usuario)):
    async with conexao() as conn:
        return await gerar_token_vinculacao(conn, u["id"])
