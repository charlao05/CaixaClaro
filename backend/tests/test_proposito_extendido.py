"""M8-D3 — proposito estendido (4 valores) + override de parecer."""
from decimal import Decimal

from caixaclaro.domain.fiscal.classificacao import (
    ContextoClassificacao,
    classificar_v2,
)
from caixaclaro.domain.fiscal.guardrails import aplicar_guardrail
from caixaclaro.domain.fiscal.triagem import triar
from caixaclaro.services.tax_opinion import generate_tax_opinion


def _pipeline(descricao, valor="100.00"):
    ctx = ContextoClassificacao(personal_rules={})
    classif = classificar_v2(descricao, Decimal(valor), ctx)
    guard = aplicar_guardrail(classif, descricao=descricao)
    tri = triar(classif, guard)
    return classif, guard, tri


def _opiniao(descricao, valor="100.00"):
    classif, guard, tri = _pipeline(descricao, valor)
    return generate_tax_opinion(
        descricao=descricao, valor=Decimal(valor),
        classif=classif, guard=guard, tri=tri,
    )


def test_aporte_capital():
    desc = "APORTE DE CAPITAL SOCIAL DO TITULAR"
    classif, _, _ = _pipeline(desc)
    assert classif.proposito == "aporte_capital"
    assert classif.origem_sugerida == "conta_propria"
    assert classif.patrimonio == "ponte_pf_pj"
    assert classif.tratamento_tributario == "isento_nao_tributavel"
    o = _opiniao(desc)
    assert "colocado no negócio" in o.fato.lower()
    assert "capital social" in (
        o.interpretacao + o.possivel_tratamento_tributario
    ).lower()


def test_dinheiro_terceiros():
    desc = "PIX RECEBIDO DINHEIRO DE TERCEIRO PARA REPASSE"
    classif, _, _ = _pipeline(desc)
    assert classif.proposito == "dinheiro_terceiros"
    assert classif.patrimonio == "transito_terceiro"
    assert classif.tratamento_tributario == "isento_nao_tributavel"
    o = _opiniao(desc)
    assert "outra pessoa" in o.fato.lower()
    assert "não é renda sua" in o.possivel_tratamento_tributario.lower()


def test_rendimento_aplicacao():
    desc = "CREDITO RENDIMENTO CDB BANCO XYZ"
    classif, _, _ = _pipeline(desc)
    assert classif.proposito == "rendimento_aplicacao"
    assert classif.origem_sugerida == "banco_financeira"
    assert classif.tratamento_tributario == "tributavel_irpf"
    o = _opiniao(desc)
    assert "rendimento" in o.fato.lower()
    assert "informe de rendimentos" in o.possivel_tratamento_tributario.lower()


def test_doacao_heranca():
    desc = "RECEBIMENTO DE DOACAO DE FAMILIAR"
    classif, _, _ = _pipeline(desc)
    assert classif.proposito == "doacao_heranca"
    assert classif.patrimonio == "pessoa_fisica"
    o = _opiniao(desc)
    assert "doação" in o.fato.lower()
    assert "itcmd" in o.possivel_tratamento_tributario.lower()
