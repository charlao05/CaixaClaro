"""Taxonomia de movimentos de estoque — módulo Meu Negócio, v1.

Mesmo padrão de domain/fiscal/taxonomia.py: identificadores imutáveis
a partir de v1. Categoria II da consulta ao CRC-ES (docs/CONSULTA_CRC_ES.md):
consolidação de eventos que o próprio usuário registra — o sistema não
infere qual produto ou quantidade corresponde a uma transação bancária.
"""
from dataclasses import dataclass
from typing import Literal

TAXONOMIA_MOVIMENTO_VERSION: str = "v1"

TipoMovimentoId = Literal[
    "entrada_compra",
    "entrada_producao",
    "entrada_ajuste",
    "entrada_devolucao",
    "saida_venda",
    "saida_perda",
    "saida_ajuste",
    "saida_devolucao",
]


@dataclass(frozen=True)
class TipoMovimento:
    id: TipoMovimentoId
    label: str
    entrada: bool
    saida: bool


TIPOS_MOVIMENTO: dict[TipoMovimentoId, TipoMovimento] = {
    "entrada_compra": TipoMovimento(
        id="entrada_compra", label="Compra / Reposição", entrada=True, saida=False,
    ),
    "entrada_producao": TipoMovimento(
        id="entrada_producao", label="Produção Própria", entrada=True, saida=False,
    ),
    "entrada_ajuste": TipoMovimento(
        id="entrada_ajuste", label="Ajuste de Inventário (entrada)", entrada=True, saida=False,
    ),
    "entrada_devolucao": TipoMovimento(
        id="entrada_devolucao", label="Devolução de Cliente", entrada=True, saida=False,
    ),
    "saida_venda": TipoMovimento(
        id="saida_venda", label="Venda", entrada=False, saida=True,
    ),
    "saida_perda": TipoMovimento(
        id="saida_perda", label="Perda / Quebra", entrada=False, saida=True,
    ),
    "saida_ajuste": TipoMovimento(
        id="saida_ajuste", label="Ajuste de Inventário (saída)", entrada=False, saida=True,
    ),
    "saida_devolucao": TipoMovimento(
        id="saida_devolucao", label="Devolução a Fornecedor", entrada=False, saida=True,
    ),
}


def tipo_movimento_valido(t: str) -> bool:
    """Retorna True se `t` é um id de tipo de movimento da taxonomia v1."""
    return t in TIPOS_MOVIMENTO


def get_tipo_movimento(t: TipoMovimentoId) -> TipoMovimento:
    """Retorna metadados do tipo de movimento."""
    return TIPOS_MOVIMENTO[t]