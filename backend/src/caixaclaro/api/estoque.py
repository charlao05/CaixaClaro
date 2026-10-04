"""Endpoints de movimentação de estoque — módulo Meu Negócio (M11)."""
from decimal import Decimal

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..api.deps import usuario_ativo
from ..db import conexao
from ..security.idempotency import executar_com_idempotencia
from ..services import estoque as estoque_service
from ..services import produtos as produtos_service

router = APIRouter()


class MovimentoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo_movimento: str
    quantidade: Decimal = Field(gt=0)
    origem: str = "manual"
    referencia_transacao_id: str | None = None
    nota: str | None = None


@router.post("/{produto_id}/movimentos", status_code=201)
async def registrar_movimento(
    produto_id: str,
    body: MovimentoIn,
    u: dict = Depends(usuario_ativo),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    async def operacao(conn):
        resp = await estoque_service.registrar_movimento(
            conn, u["id"], produto_id,
            tipo_movimento=body.tipo_movimento,
            quantidade=body.quantidade,
            origem=body.origem,
            referencia_transacao_id=body.referencia_transacao_id,
            nota=body.nota,
        )
        return resp, 201

    resp, status_http = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota=f"POST /api/v1/produtos/{produto_id}/movimentos",
        chave=idempotency_key,
        body=body.model_dump(mode="json"),
        operacao=operacao,
    )
    return JSONResponse(content=resp, status_code=status_http)


@router.get("/{produto_id}/movimentos")
async def listar_movimentos(produto_id: str, u: dict = Depends(usuario_ativo)):
    async with conexao() as conn:
        await produtos_service.obter(conn, u["id"], produto_id)  # valida posse
        itens = await estoque_service.listar_movimentos(conn, u["id"], produto_id)
    return {"itens": itens}


@router.get("/{produto_id}/saldo")
async def saldo(produto_id: str, u: dict = Depends(usuario_ativo)):
    async with conexao() as conn:
        await produtos_service.obter(conn, u["id"], produto_id)
        s = await estoque_service.saldo_atual(conn, u["id"], produto_id)
    return {"product_id": produto_id, "saldo": str(s)}