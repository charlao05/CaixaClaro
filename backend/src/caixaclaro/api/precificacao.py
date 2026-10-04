"""Endpoint de precificação — Categoria I da consulta ao CRC-ES.

Ver docs/CONSULTA_CRC_ES.md e docs/REGRA_ORIENTADOR.md: cálculo puro
sobre dado informado, nunca recomendação.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ..api.deps import usuario_ativo
from ..db import conexao
from ..services import precificacao as precificacao_service

router = APIRouter()


class CenarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=1, max_length=100)
    preco: Decimal
    custo_variavel_unitario: Decimal
    custos_fixos_periodo: Decimal | None = None
    volume_hipotese: Decimal | None = None


class PrecificarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cenarios: list[CenarioIn] = Field(min_length=1, max_length=2)
    salvar: bool = False
    product_id: str | None = None


@router.post("/calcular")
async def calcular(body: PrecificarIn, u: dict = Depends(usuario_ativo)):
    cenarios_in = [c.model_dump(mode="json") for c in body.cenarios]
    async with conexao() as conn:
        return await precificacao_service.calcular(
            conn, u["id"], cenarios_in,
            salvar=body.salvar, product_id=body.product_id,
        )