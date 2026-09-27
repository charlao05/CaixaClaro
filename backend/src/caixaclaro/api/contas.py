"""Endpoints de contas e conexao bancaria (M3b).

Escopo atual: apenas POST /contas/conectar.
Demais endpoints e webhook entram em passos seguintes.
"""
from fastapi import APIRouter, Depends

from ..api.deps import usuario
from ..db import conexao
from ..services.pluggy import criar_connect_token

router = APIRouter()


@router.post("/conectar")
async def conectar(u: dict = Depends(usuario)):
    return await criar_connect_token(u["id"])

@router.get("")
async def listar_contas(u: dict = Depends(usuario)):
    async with conexao() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id, a.provider, a.provider_account_id, a.nome, a.criado_em
              FROM accounts a
             WHERE a.user_id = $1
               AND NOT EXISTS (
                 SELECT 1 FROM consents c
                  WHERE c.provider = a.provider
                    AND c.provider_user_id = a.item_id
                    AND c.user_id = a.user_id
                    AND c.revogado_em IS NOT NULL
               )
             ORDER BY a.criado_em DESC, a.id DESC
            """,
            u["id"],
        )
    return {
        "itens": [
            {
                "id": str(r["id"]),
                "provider": r["provider"],
                "provider_account_id": r["provider_account_id"],
                "nome": r["nome"],
                "criado_em": r["criado_em"].isoformat(),
            }
            for r in rows
        ]
    }

@router.post("/{id}/revogar")
async def revogar_conta(id: str, u: dict = Depends(usuario)):
    from ..services.contas import revogar_item
    async with conexao() as conn:
        return await revogar_item(conn, u["id"], id)

@router.post("/{id}/sync", status_code=202)
async def sincronizar_conta(id: str, u: dict = Depends(usuario)):
    from ..services.contas import iniciar_sync
    async with conexao() as conn:
        return await iniciar_sync(conn, u["id"], id)

