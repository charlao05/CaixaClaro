"""Integracao M4b — pipeline fiscal -> transactions -> fiscal_state -> alerts.

Cobre os 10 casos do plano M4b. Testes de servico (puros) usam
funcoes de services/*; testes HTTP usam a app FastAPI.
"""
from datetime import date
from decimal import Decimal

import pytest

from caixaclaro.domain.fiscal.classificacao import ContextoClassificacao
from caixaclaro.services.faturamento import (
    FAIXAS,
    TETO_MEI_ANUAL,
    atualizar_fiscal_state,
    calcular_delta,
    conta_faturamento,
    faixa_cruzada,
    prazo_do_ano,
)
from caixaclaro.services.fiscal import processar_lancamento


# ============================================================
# Servico — pipeline (testes 1, 2, 3)
# ============================================================

def test_pipeline_produz_categoria_e_proposito():
    ctx = ContextoClassificacao(personal_rules={})
    r = processar_lancamento(
        "PAGTO GUIA DAS SIMPLES", Decimal("100.00"), contexto=ctx
    )
    assert r.classificacao.categoria == "imposto_das"
    assert r.classificacao.proposito is not None


def test_pipeline_preserva_classificacao_ja_correta():
    """Classificador acerta `emprestimo`; guardrail §6.1 nao altera.

    A prova de que o guardrail *reescreve* receita errada para
    `emprestimo` esta em tests/test_guardrails.py (fabricando um
    ClassificacaoResultado com categoria errada). Aqui, o pipeline
    completo e exercitado: classificador + guardrail + triagem
    concordam, e nada e sobrescrito.
    """
    ctx = ContextoClassificacao(personal_rules={})
    r = processar_lancamento(
        "CREDITO EMPRESTIMO CONSIGNADO BCO",
        Decimal("500.00"),
        contexto=ctx,
    )
    assert r.classificacao.categoria == "emprestimo"
    assert r.guardrail.aplicado is False
    assert r.guardrail.categoria_corrigida == "emprestimo"


def test_triagem_define_needs_review():
    ctx = ContextoClassificacao(personal_rules={})
    r = processar_lancamento(
        "PIX RECEBIDO JOAO", Decimal("100.00"), contexto=ctx
    )
    assert r.triagem.disposicao == "fila_revisao"
    assert r.triagem.needs_review is True


# ============================================================
# Faturamento §9 (testes 4, 5)
# ============================================================

def test_faturamento_so_conta_receita_negocio():
    assert conta_faturamento("atividade_negocio", "receita_servico") is True
    assert conta_faturamento("atividade_negocio", "receita_venda") is True
    assert conta_faturamento("atividade_negocio", "custo_operacional") is False
    assert conta_faturamento("pessoa_fisica", "receita_servico") is False


def test_salario_nao_incrementa_faturamento():
    estado, r = calcular_delta(
        {"faturamento_acumulado": "1000.00", "ano_referencia": 2026},
        Decimal("0"),
        date(2026, 9, 27),
    )
    assert r.depois == Decimal("1000.00")
    assert r.faixas == ()


# ============================================================
# Faixas §10 (testes 6, 7)
# ============================================================

def test_cruzamento_de_faixa():
    antes = TETO_MEI_ANUAL * Decimal("0.55")
    depois = TETO_MEI_ANUAL * Decimal("0.65")
    faixas = faixa_cruzada(antes, depois)
    assert len(faixas) == 1
    slug, sev, _ = faixas[0]
    assert slug == "enq_MEI_60"
    assert sev == "informativo"


def test_mesma_faixa_nao_duplica_alerta():
    antes = TETO_MEI_ANUAL * Decimal("0.61")
    depois = TETO_MEI_ANUAL * Decimal("0.62")
    assert faixa_cruzada(antes, depois) == []


def test_multiplas_faixas_de_uma_vez():
    antes = TETO_MEI_ANUAL * Decimal("0.55")
    depois = TETO_MEI_ANUAL * Decimal("0.96")
    slugs = [f[0] for f in faixa_cruzada(antes, depois)]
    assert slugs == ["enq_MEI_60", "enq_MEI_80", "enq_MEI_90", "enq_MEI_95"]


# ============================================================
# Reset por ano (M4b-D2)
# ============================================================

def test_reset_por_ano():
    estado, r = calcular_delta(
        {"faturamento_acumulado": "50000.00", "ano_referencia": 2025},
        Decimal("1000.00"),
        date(2026, 1, 5),
    )
    assert estado["ano_referencia"] == 2026
    assert r.antes == Decimal("0")
    assert r.depois == Decimal("1000.00")


def test_prazo_e_fim_do_ano():
    assert prazo_do_ano(date(2026, 9, 27)) == date(2026, 12, 31)
    assert prazo_do_ano(date(2027, 1, 1)) == date(2027, 12, 31)
