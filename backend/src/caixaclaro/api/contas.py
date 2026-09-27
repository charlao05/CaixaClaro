"""Endpoints de contas e conexao bancaria (M3b).

Escopo atual: apenas POST /contas/conectar.
Demais endpoints e webhook entram em passos seguintes.
"""
from fastapi import APIRouter, Depends

from ..api.deps import usuario
from ..services.pluggy import criar_connect_token

router = APIRouter()


@router.post("/conectar")
async def conectar(u: dict = Depends(usuario)):
    return await criar_connect_token(u["id"])
