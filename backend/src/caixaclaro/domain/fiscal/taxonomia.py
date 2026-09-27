"""Taxonomia fiscal v1 — CONTRATOS_INTERNOS §4.1.

Define os valores válidos de `categoria` em ClassificacaoResultado.
Contrato normativo; identificadores são imutáveis a partir de v1.
"""
from dataclasses import dataclass
from typing import Literal

TAXONOMIA_VERSION: str = "v1"

CategoriaId = Literal[
    "receita_servico",
    "receita_venda",
    "salario",
    "imposto_das",
    "taxas_tarifas",
    "custo_operacional",
    "transferencia_propria",
    "pessoal_prolabore",
    "reembolso",
    "emprestimo",
    "outros",
]


@dataclass(frozen=True)
class Categoria:
    id: CategoriaId
    label: str
    receita: bool
    despesa: bool
    neutra: bool


CATEGORIAS: dict[CategoriaId, Categoria] = {
    "receita_servico": Categoria(
        id="receita_servico",
        label="Trabalho / Prestação de Serviço",
        receita=True, despesa=False, neutra=False,
    ),
    "receita_venda": Categoria(
        id="receita_venda",
        label="Vendas de Produtos / Comércio",
        receita=True, despesa=False, neutra=False,
    ),
    "salario": Categoria(
        id="salario",
        label="Salário Formal / Aposentadoria",
        receita=True, despesa=False, neutra=False,
    ),
    "imposto_das": Categoria(
        id="imposto_das",
        label="Impostos e Tributos (DAS/IRPF/DARF)",
        receita=False, despesa=True, neutra=False,
    ),
    "taxas_tarifas": Categoria(
        id="taxas_tarifas",
        label="Taxas Bancárias & Maquininha",
        receita=False, despesa=True, neutra=False,
    ),
    "custo_operacional": Categoria(
        id="custo_operacional",
        label="Gastos da Atividade / Trabalho",
        receita=False, despesa=True, neutra=False,
    ),
    "transferencia_propria": Categoria(
        id="transferencia_propria",
        label="Transferência Entre Contas Próprias",
        receita=False, despesa=False, neutra=True,
    ),
    "pessoal_prolabore": Categoria(
        id="pessoal_prolabore",
        label="Retirada da Empresa / Pró-Labore",
        receita=False, despesa=False, neutra=True,
    ),
    "reembolso": Categoria(
        id="reembolso",
        label="Devolução / Reembolso",
        receita=False, despesa=False, neutra=True,
    ),
    "emprestimo": Categoria(
        id="emprestimo",
        label="Empréstimo (peguei ou emprestei)",
        receita=False, despesa=False, neutra=True,
    ),
    "outros": Categoria(
        id="outros",
        label="Aguardando Confirmação",
        receita=False, despesa=False, neutra=True,
    ),
}


def categoria_valida(c: str) -> bool:
    """Retorna True se `c` é um id de categoria da taxonomia v1."""
    return c in CATEGORIAS


def get_categoria(c: CategoriaId) -> Categoria:
    """Retorna metadados da categoria."""
    return CATEGORIAS[c]
