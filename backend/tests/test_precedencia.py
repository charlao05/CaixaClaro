"""§19.4 — test_precedencia.

- personal_rule vence heuristica
- guardrail vence personal_rule
"""
from decimal import Decimal

from caixaclaro.domain.fiscal.classificacao import (
    ContextoClassificacao,
    classificar_v2,
)
from caixaclaro.domain.fiscal.guardrails import aplicar_guardrail


def test_personal_rule_vence_heuristica():
    # "PIX RECEBIDO JOAO" cai em outros pela heuristica.
    ctx = ContextoClassificacao(
        personal_rules={"PIX RECEBIDO JOAO": "receita_servico"}
    )
    r = classificar_v2("PIX RECEBIDO JOAO", Decimal("100.00"), ctx)
    assert r.categoria == "receita_servico"
    assert r.via == "regra_personalizada"


def test_guardrail_vence_personal_rule():
    # personal_rule mapeia para receita_servico; guardrail §6.1
    # reescreve porque a descricao contem "emprestimo".
    ctx = ContextoClassificacao(
        personal_rules={"PAGTO EMPRESTIMO": "receita_servico"}
    )
    classif = classificar_v2("PAGTO EMPRESTIMO", Decimal("100.00"), ctx)
    assert classif.categoria == "receita_servico"  # personal rule venceu

    guard = aplicar_guardrail(classif, descricao="PAGTO EMPRESTIMO")
    assert guard.aplicado is True
    assert guard.categoria_corrigida == "emprestimo"
    assert guard.regra_acionada == "emprestimo"
