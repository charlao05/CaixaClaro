"""Regras puras de estoque — módulo Meu Negócio.

Categoria II da consulta ao CRC-ES (docs/CONSULTA_CRC_ES.md):
consolidação matemática de eventos que o usuário já registrou — soma e
subtração, sem classificação ou interpretação nova.

Invariante NUNCA deste módulo: o saldo nunca fica negativo. Nenhum
tipo de movimento, incluindo ajuste, pode levar o saldo abaixo de
zero — uma correção que exigiria saldo negativo deve ser resolvida
revisando o histórico de movimentos, não forçando um valor negativo.
"""
from decimal import Decimal

ENTRADA: frozenset[str] = frozenset(
    {"entrada_compra", "entrada_producao", "entrada_ajuste", "entrada_devolucao"}
)
SAIDA: frozenset[str] = frozenset(
    {"saida_venda", "saida_perda", "saida_ajuste", "saida_devolucao"}
)


class EstoqueNegativoRecusado(Exception):
    """O movimento foi recusado porque deixaria o saldo negativo.

    Esta é uma recusa deliberada (REGRA_ORIENTADOR.md §3: "o sistema
    pode se recusar a calcular"), não um erro inesperado.
    """

    def __init__(self, saldo_atual: Decimal, quantidade: Decimal):
        self.saldo_atual = saldo_atual
        self.quantidade = quantidade
        super().__init__(
            f"Movimento recusado: saldo atual {saldo_atual}, "
            f"saída de {quantidade} deixaria o estoque negativo."
        )


def tipo_e_entrada(tipo_movimento: str) -> bool:
    return tipo_movimento in ENTRADA


def tipo_e_saida(tipo_movimento: str) -> bool:
    return tipo_movimento in SAIDA


def aplicar_movimento(
    saldo_atual: Decimal, tipo_movimento: str, quantidade: Decimal
) -> Decimal:
    """Retorna o novo saldo após o movimento.

    Levanta EstoqueNegativoRecusado em vez de retornar um valor
    negativo. Levanta ValueError se o tipo de movimento não pertencer
    nem a ENTRADA nem a SAIDA — chamar `tipo_movimento_valido` antes
    é responsabilidade de quem chama esta função.
    """
    if tipo_e_entrada(tipo_movimento):
        return saldo_atual + quantidade
    if tipo_e_saida(tipo_movimento):
        novo_saldo = saldo_atual - quantidade
        if novo_saldo < 0:
            raise EstoqueNegativoRecusado(saldo_atual, quantidade)
        return novo_saldo
    raise ValueError(f"tipo_movimento desconhecido: {tipo_movimento}")