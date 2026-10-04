"""Testes puros de domain/negocio/estoque.py — sem banco.

Invariante NUNCA: estoque não fica negativo.
"""
from decimal import Decimal

import pytest

from caixaclaro.domain.negocio.estoque import (
    EstoqueNegativoRecusado,
    aplicar_movimento,
)


def test_entrada_soma():
    assert aplicar_movimento(Decimal(10), "entrada_compra", Decimal(5)) == Decimal(15)


def test_saida_subtrai():
    assert aplicar_movimento(Decimal(10), "saida_venda", Decimal(3)) == Decimal(7)


def test_saida_exata_zera_sem_erro():
    assert aplicar_movimento(Decimal(10), "saida_venda", Decimal(10)) == Decimal(0)


def test_nunca_estoque_negativo_saida_venda():
    with pytest.raises(EstoqueNegativoRecusado) as exc:
        aplicar_movimento(Decimal(5), "saida_venda", Decimal(6))
    assert exc.value.saldo_atual == Decimal(5)
    assert exc.value.quantidade == Decimal(6)


def test_nunca_estoque_negativo_mesmo_em_ajuste():
    """Decisão deliberada: nem ajuste pode forçar saldo negativo."""
    with pytest.raises(EstoqueNegativoRecusado):
        aplicar_movimento(Decimal(2), "saida_ajuste", Decimal(3))


def test_nunca_estoque_negativo_perda():
    with pytest.raises(EstoqueNegativoRecusado):
        aplicar_movimento(Decimal(0), "saida_perda", Decimal(1))


def test_tipo_movimento_desconhecido_levanta_value_error():
    with pytest.raises(ValueError):
        aplicar_movimento(Decimal(10), "tipo_inventado", Decimal(1))


@pytest.mark.parametrize("tipo", [
    "entrada_compra", "entrada_producao", "entrada_ajuste", "entrada_devolucao",
])
def test_todos_tipos_entrada_somam(tipo):
    assert aplicar_movimento(Decimal(0), tipo, Decimal(1)) == Decimal(1)


@pytest.mark.parametrize("tipo", [
    "saida_venda", "saida_perda", "saida_ajuste", "saida_devolucao",
])
def test_todos_tipos_saida_subtraem(tipo):
    assert aplicar_movimento(Decimal(5), tipo, Decimal(1)) == Decimal(4)