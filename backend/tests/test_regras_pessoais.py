"""Regras pessoais aprendidas respeitam a direção do dinheiro.

Defeito encontrado na revisão do M13 (docs/AUDITORIA_JORNADA_2026-10-09.md,
seção 8, R1): a regra gravava a direção do lançamento em que foi aprendida,
mas a leitura ignorava. Uma resposta dada a uma SAÍDA era aplicada em
silêncio a uma ENTRADA com a mesma descrição — e há bancos cuja descrição é
idêntica nos dois sentidos.
"""
from decimal import Decimal

from caixaclaro.domain.fiscal.classificacao import (
    ContextoClassificacao,
    RegraPessoal,
    classificar_v2,
    direcao_do_valor,
)

DESCRICAO = "PIX TRANSF JOAO S05/10"

GASTO_NA_SAIDA = RegraPessoal(
    padrao="pix transf joao s05/10",
    categoria="custo_operacional",
    proposito="gasto_negocio",
    direcao="saida",
)
TRABALHO_NA_ENTRADA = RegraPessoal(
    padrao="pix transf joao s05/10",
    categoria="receita_servico",
    proposito="trabalho_servico",
    direcao="entrada",
)


def _ctx(*regras, personal_rules=None):
    return ContextoClassificacao(
        personal_rules=personal_rules or {}, regras_pessoais=tuple(regras)
    )


def test_direcao_vem_do_sinal_do_valor():
    assert direcao_do_valor(Decimal("-0.01")) == "saida"
    assert direcao_do_valor(Decimal("0.01")) == "entrada"
    assert direcao_do_valor(Decimal("0")) == "entrada"
    assert direcao_do_valor(None) is None


def test_regra_aprendida_na_saida_vale_para_saida():
    r = classificar_v2(DESCRICAO, Decimal("-100.00"), _ctx(GASTO_NA_SAIDA))
    assert r.categoria == "custo_operacional"
    assert r.proposito == "gasto_negocio"
    assert r.via == "regra_personalizada"
    assert r.needs_review is False


def test_regra_aprendida_na_saida_nao_vale_para_entrada():
    r = classificar_v2(DESCRICAO, Decimal("300.00"), _ctx(GASTO_NA_SAIDA))
    assert r.categoria == "outros"
    assert r.via == "heuristica"
    assert r.needs_review is True


def test_regra_aprendida_na_entrada_nao_vale_para_saida():
    r = classificar_v2(DESCRICAO, Decimal("-80.00"), _ctx(TRABALHO_NA_ENTRADA))
    assert r.categoria == "outros"
    assert r.needs_review is True


def test_regras_dos_dois_sentidos_convivem_em_qualquer_ordem():
    for regras in (
        (GASTO_NA_SAIDA, TRABALHO_NA_ENTRADA),
        (TRABALHO_NA_ENTRADA, GASTO_NA_SAIDA),
    ):
        ctx = _ctx(*regras)
        saida = classificar_v2(DESCRICAO, Decimal("-100.00"), ctx)
        entrada = classificar_v2(DESCRICAO, Decimal("300.00"), ctx)
        assert saida.categoria == "custo_operacional"
        assert entrada.categoria == "receita_servico"
        assert entrada.patrimonio == "atividade_negocio"


def test_regra_sem_direcao_vale_para_os_dois_sentidos():
    regra = RegraPessoal(padrao="mercadinho do bairro", categoria="custo_operacional")
    ctx = _ctx(regra)
    for valor in ("-25.00", "25.00"):
        r = classificar_v2("COMPRA MERCADINHO DO BAIRRO", Decimal(valor), ctx)
        assert r.categoria == "custo_operacional"
        assert r.via == "regra_personalizada"


def test_regra_com_direcao_nao_vale_quando_a_direcao_e_desconhecida():
    r = classificar_v2(DESCRICAO, None, _ctx(GASTO_NA_SAIDA))
    assert r.categoria == "outros"
    assert r.needs_review is True


def test_primeira_regra_que_casa_vence():
    especifica = RegraPessoal(
        padrao="pix recebido clinica sorriso ltda",
        categoria="receita_servico", direcao="entrada",
    )
    generica = RegraPessoal(
        padrao="pix recebido", categoria="transferencia_propria", direcao="entrada",
    )
    r = classificar_v2(
        "PIX RECEBIDO CLINICA SORRISO LTDA", Decimal("300.00"),
        _ctx(especifica, generica),
    )
    assert r.categoria == "receita_servico"


def test_regra_com_categoria_desconhecida_e_ignorada():
    regra = RegraPessoal(padrao="pix transf joao", categoria="nao_existe", direcao="saida")
    r = classificar_v2(DESCRICAO, Decimal("-100.00"), _ctx(regra))
    assert r.categoria == "outros"
    assert r.via == "heuristica"


def test_regra_aprendida_vem_antes_do_dicionario_do_contrato():
    ctx = _ctx(GASTO_NA_SAIDA, personal_rules={"PIX TRANSF JOAO": "emprestimo"})
    assert classificar_v2(DESCRICAO, Decimal("-100.00"), ctx).categoria == "custo_operacional"
    # No sentido em que a regra aprendida não vale, o dicionário do contrato
    # original (sem direção) continua valendo.
    assert classificar_v2(DESCRICAO, Decimal("100.00"), ctx).categoria == "emprestimo"


def test_fato_do_extrato_continua_vencendo_a_regra():
    # Regra sem direção que aponta para uma categoria só de entrada, aplicada
    # a uma saída: a contradição manda para a revisão (decisão D3 do M13).
    regra = RegraPessoal(padrao="pix transf joao", categoria="receita_servico")
    r = classificar_v2(DESCRICAO, Decimal("-100.00"), _ctx(regra))
    assert r.categoria == "outros"
    assert r.needs_review is True


def test_motivo_da_regra_aprendida_nao_leva_identificador_interno():
    # O motivo pode aparecer na tela de revisão.
    r = classificar_v2(DESCRICAO, Decimal("-100.00"), _ctx(GASTO_NA_SAIDA))
    assert "custo_operacional" not in r.motivo
    assert "->" not in r.motivo
    assert r.motivo == "Você já respondeu antes um lançamento com esta descrição."
