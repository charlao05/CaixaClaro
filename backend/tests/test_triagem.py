from decimal import Decimal

from caixaclaro.domain.fiscal.classificacao import (
    ClassificacaoResultado,
    ContextoClassificacao,
    classificar_v2,
)
from caixaclaro.domain.fiscal.guardrails import aplicar_guardrail
from caixaclaro.domain.fiscal.triagem import triar


def _fluxo(desc, valor=100.0):
    ctx = ContextoClassificacao(personal_rules={})
    classif = classificar_v2(desc, Decimal(str(valor)), ctx)
    guard = aplicar_guardrail(classif, descricao=desc)
    return triar(classif, guard)


def _classif(*, categoria, proposito, patrimonio, tratamento, confianca,
             via, needs_review):
    return ClassificacaoResultado(
        categoria=categoria, proposito=proposito,
        origem_sugerida="desconhecido", patrimonio=patrimonio,
        tratamento_tributario=tratamento, confianca=confianca,
        needs_review=needs_review, via=via, motivo=None,
    )


# ============================================================
# fila_revisao
# ============================================================

def test_outros_vai_para_fila():
    r = _fluxo("PIX RECEBIDO JOAO")
    assert r.disposicao == "fila_revisao"
    assert r.needs_review is True


def test_confianca_baixa_vai_para_fila():
    c = _classif(
        categoria="receita_servico", proposito="trabalho_servico",
        patrimonio="atividade_negocio", tratamento="tributavel_irpf",
        confianca=0.65, via="heuristica", needs_review=False,
    )
    from caixaclaro.domain.fiscal.guardrails import GuardrailResultado
    g = GuardrailResultado(
        aplicado=False, categoria_original="receita_servico",
        categoria_corrigida="receita_servico", motivo="",
        regra_acionada=None,
    )
    r = triar(c, g)
    assert r.disposicao == "fila_revisao"


# ============================================================
# confirmacao
# ============================================================

def test_guardrail_critico_vai_para_confirmacao():
    """Pro-labore é guardrail ponte_pf_pj — crítico."""
    r = _fluxo("TRANSF PRO LABORE TITULAR")
    assert r.disposicao == "confirmacao"
    assert r.needs_review is True


def test_confianca_media_vai_para_confirmacao():
    c = _classif(
        categoria="custo_operacional", proposito="gasto_negocio",
        patrimonio="atividade_negocio", tratamento="indeterminado_pendente",
        confianca=0.80, via="heuristica", needs_review=False,
    )
    from caixaclaro.domain.fiscal.guardrails import GuardrailResultado
    g = GuardrailResultado(
        aplicado=False, categoria_original="custo_operacional",
        categoria_corrigida="custo_operacional", motivo="",
        regra_acionada=None,
    )
    r = triar(c, g)
    assert r.disposicao == "confirmacao"


# ============================================================
# silencioso
# ============================================================

def test_imposto_vai_para_silencioso():
    r = _fluxo("PAGTO GUIA DAS SIMPLES")
    assert r.disposicao == "silencioso"
    assert r.needs_review is False


def test_receita_servico_pj_vai_para_silencioso():
    r = _fluxo("CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA")
    assert r.disposicao == "silencioso"


# ============================================================
# Exclusividade — um caso, uma disposição
# ============================================================

def test_exclusividade_mutua():
    """Cada entrada cai em exatamente uma disposição."""
    descs = [
        "PIX RECEBIDO JOAO",              # fila
        "TRANSF PRO LABORE TITULAR",       # confirmacao
        "PAGTO GUIA DAS SIMPLES",          # silencioso
        "POSTO IPIRANGA",                  # silencioso
        "ESTORNO UBER",                    # confirmacao
    ]
    for desc in descs:
        r = _fluxo(desc)
        assert r.disposicao in ("silencioso", "confirmacao", "fila_revisao")
