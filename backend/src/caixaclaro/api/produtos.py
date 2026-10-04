"""Endpoints de produtos/serviços — módulo Meu Negócio (M11)."""
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ..api.deps import usuario_ativo
from ..db import conexao
from ..services import produtos as produtos_service

router = APIRouter()


class ProdutoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo: Literal["produto", "servico"]
    nome: str = Field(min_length=1, max_length=200)
    unidade_medida: str = Field(default="un", max_length=20)
    custo_atual: Decimal | None = None
    preco_atual: Decimal | None = None
    controla_estoque: bool = True


class ProdutoPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    unidade_medida: str | None = None
    custo_atual: Decimal | None = None
    preco_atual: Decimal | None = None
    controla_estoque: bool | None = None
    ativo: bool | None = None


@router.post("", status_code=201)
async def criar_produto(body: ProdutoIn, u: dict = Depends(usuario_ativo)):
    async with conexao() as conn:
        return await produtos_service.criar(
            conn, u["id"],
            tipo=body.tipo, nome=body.nome, unidade_medida=body.unidade_medida,
            custo_atual=body.custo_atual, preco_atual=body.preco_atual,
            controla_estoque=body.controla_estoque,
        )


@router.get("")
async def listar_produtos(apenas_ativos: bool = True, u: dict = Depends(usuario_ativo)):
    async with conexao() as conn:
        itens = await produtos_service.listar(conn, u["id"], apenas_ativos=apenas_ativos)
    return {"itens": itens}


@router.get("/{produto_id}")
async def obter_produto(produto_id: str, u: dict = Depends(usuario_ativo)):
    async with conexao() as conn:
        return await produtos_service.obter(conn, u["id"], produto_id)


@router.patch("/{produto_id}")
async def atualizar_produto(
    produto_id: str, body: ProdutoPatch, u: dict = Depends(usuario_ativo)
):
    campos = body.model_dump(exclude_unset=True)
    async with conexao() as conn:
        return await produtos_service.atualizar(conn, u["id"], produto_id, campos)