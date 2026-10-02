"""Consulta de sincronizacao bancaria (M3b).

Escopo: leitura de sync_requests. Execucao e responsabilidade de M6.
"""
from fastapi import APIRouter, Depends

from ..api.deps import usuario_ativo
from ..db import conexao
from ..services.contas import obter_sync

router = APIRouter()


@router.get("/{sync_id}")
async def consultar_sync(sync_id: str, u: dict = Depends(usuario_ativo)):
    async with conexao() as conn:
        return await obter_sync(conn, u["id"], sync_id)
