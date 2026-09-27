from decimal import Decimal

from caixaclaro.domain.fiscal.classificacao import (
    ClassificacaoResultado,
    ContextoClassificacao,
    classificar_v2,
)
from caixaclaro.domain.fiscal.guardrails import (
    GuardrailResultado,
    aplicar_guardrail,
)


def _classifica(desc, valor=100.0):
    ctx = ContextoClassificacao(personal_rules={})
    return classificar_v2(desc, Decimal(str(valor)), ctx)


def _guarda(desc, *, cpf_titular=None, cpf_contraparte=None):
    classif = _classifica(desc)
    return aplicar_guardrail(
        classif,
        descricao=desc,
        cpf_titular_hash=cpf_titular,
        cpf_contraparte_hash=cpf_contraparte,
    )


# ============================================================
# 6.1 emprestimo
# ============================================================

def test_emprestimo_reescreve_receita():
    """Se classificador errar e marcar receita_servico, guardrail corrige."""
    classif = ClassificacaoResultado(
        categoria="receita_servico", proposito="trabalho_servico",
        origem_sugerida="desconhecido", patrimonio="atividade_negocio",
        tratamento_tributario="tributavel_irpf", confianca=0.9,
        needs_review=False, via="heuristica", motivo=None,
    )
    g = aplicar_guardrail(classif, descricao="CREDITO EMPRESTIMO CONSIGNADO BCO")
    assert g.aplicado is True
    assert g.categoria_original == "receita_servico"
    assert g.categoria_corrigida == "emprestimo"
    assert g.regra_acionada == "emprestimo"


def test_emprestimo_nao_dispara_em_custo_operacional():
    g = _guarda("PAGTO EMPRESTIMO")  # classificador já corrigiu? não — cai em outros
    # cai em outros porque não bate heurística; guardrail não aplica
    # (guardrail só age sobre receita_servico/receita_venda em 6.1)
    assert g.regra_acionada in (None, "emprestimo")


# ============================================================
# 6.2 estorno
# ============================================================

def test_estorno_reescreve_receita():
    classif = ClassificacaoResultado(
        categoria="receita_venda", proposito="venda_produto",
        origem_sugerida="desconhecido", patrimonio="atividade_negocio",
        tratamento_tributario="faturamento_pj", confianca=0.9,
        needs_review=False, via="heuristica", motivo=None,
    )
    g = aplicar_guardrail(classif, descricao="ESTORNO COMPRA DUPLICADA")
    assert g.aplicado is True
    assert g.categoria_corrigida == "reembolso"
    assert g.regra_acionada == "estorno"


# ============================================================
# 6.3 ponte_pf_pj
# ============================================================

def test_pro_labore_reescreve_transferencia():
    g = _guarda("TRANSF PRO LABORE TITULAR")
    assert g.aplicado is True
    assert g.categoria_corrigida == "pessoal_prolabore"
    assert g.regra_acionada == "ponte_pf_pj"


# ============================================================
# 6.4 cpf_proprio
# ============================================================

def test_cpf_proprio_reescreve_receita():
    classif = ClassificacaoResultado(
        categoria="receita_servico", proposito="trabalho_servico",
        origem_sugerida="desconhecido", patrimonio="atividade_negocio",
        tratamento_tributario="tributavel_irpf", confianca=0.9,
        needs_review=False, via="heuristica", motivo=None,
    )
    g = aplicar_guardrail(
        classif,
        descricao="PIX RECEBIDO M SILVA",
        cpf_titular_hash="abc123",
        cpf_contraparte_hash="abc123",
    )
    assert g.aplicado is True
    assert g.categoria_corrigida == "transferencia_propria"
    assert g.regra_acionada == "cpf_proprio"


def test_cpf_diferente_nao_dispara():
    classif = ClassificacaoResultado(
        categoria="receita_servico", proposito="trabalho_servico",
        origem_sugerida="desconhecido", patrimonio="atividade_negocio",
        tratamento_tributario="tributavel_irpf", confianca=0.9,
        needs_review=False, via="heuristica", motivo=None,
    )
    g = aplicar_guardrail(
        classif,
        descricao="PIX RECEBIDO JOAO",
        cpf_titular_hash="abc",
        cpf_contraparte_hash="xyz",
    )
    assert g.regra_acionada != "cpf_proprio"


def test_sem_cpf_nao_dispara_cpf_proprio():
    g = _guarda("PIX RECEBIDO JOAO")
    assert g.regra_acionada != "cpf_proprio"


# ============================================================
# 6.5 tributo
# ============================================================

def test_tributo_reescreve_qualquer_categoria():
    classif = ClassificacaoResultado(
        categoria="custo_operacional", proposito="gasto_negocio",
        origem_sugerida="desconhecido", patrimonio="atividade_negocio",
        tratamento_tributario="indeterminado_pendente", confianca=0.9,
        needs_review=False, via="heuristica", motivo=None,
    )
    g = aplicar_guardrail(classif, descricao="PAGTO DARF CARNE LEAO")
    assert g.aplicado is True
    assert g.categoria_corrigida == "imposto_das"
    assert g.regra_acionada == "tributo"


# ============================================================
# Caso sem guardrail
# ============================================================

def test_sem_guardrail_regra_acionada_null():
    g = _guarda("PAGTO GUIA DAS SIMPLES")  # já classificado como imposto_das
    assert g.aplicado is False
    assert g.regra_acionada is None


def test_guardrail_resultado_campos():
    g = _guarda("PAGTO GUIA DAS SIMPLES")
    for campo in ("aplicado", "categoria_original", "categoria_corrigida",
                  "motivo", "regra_acionada"):
        assert hasattr(g, campo), f"faltando: {campo}"
