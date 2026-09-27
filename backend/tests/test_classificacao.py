from decimal import Decimal
from typing import get_args

import pytest

from caixaclaro.domain.fiscal.classificacao import (
    ContextoClassificacao,
    PropositoId,
    classificar_v2,
)


def _ctx(**kw):
    return ContextoClassificacao(personal_rules=kw.pop("personal_rules", {}), **kw)


def _classifica(desc, valor=100.0, ctx=None):
    return classificar_v2(desc, Decimal(str(valor)), ctx or _ctx())


def test_resultado_tem_os_nove_campos():
    r = _classifica("PAGTO GUIA DAS SIMPLES")
    for campo in ("categoria", "proposito", "origem_sugerida",
                  "patrimonio", "tratamento_tributario", "confianca",
                  "needs_review", "via", "motivo"):
        assert hasattr(r, campo), f"faltando: {campo}"


def test_confianca_no_intervalo():
    for desc in ["PAGTO GUIA DAS", "PIX RECEBIDO JOAO", "PRO LABORE TITULAR",
                 "POSTO IPIRANGA", "ESTORNO UBER"]:
        r = _classifica(desc)
        assert 0.0 <= r.confianca <= 1.0, f"{desc}: {r.confianca}"


def test_via_apenas_personalizada_ou_heuristica():
    r = _classifica("PIX RECEBIDO")
    assert r.via in ("regra_personalizada", "heuristica")


def test_das_simples():
    r = _classifica("PAGTO GUIA DAS SIMPLES NACIONAL")
    assert r.categoria == "imposto_das"
    assert r.via == "heuristica"
    assert r.needs_review is False


def test_darf():
    r = _classifica("DARF CARNE LEAO MENSAL")
    assert r.categoria == "imposto_das"


def test_salario():
    r = _classifica("CREDITO TED FOLHA PAGTO SALARIO")
    assert r.categoria == "salario"
    assert r.patrimonio == "pessoa_fisica"
    assert r.tratamento_tributario == "retencao_fonte"


def test_beneficio_inss():
    r = _classifica("BENEFICIO INSS APOSENTADORIA")
    assert r.categoria == "salario"


def test_emprestimo():
    r = _classifica("CREDITO LIBERACAO EMPRESTIMO CONSIGNADO BCO")
    assert r.categoria == "emprestimo"
    assert r.patrimonio == "pessoa_fisica"


def test_estorno():
    r = _classifica("ESTORNO COMPRA DUPLICADA UBER")
    assert r.categoria == "reembolso"
    assert r.needs_review is False


def test_devolucao():
    r = _classifica("DEVOLUCAO PIX RECEBIDO")
    assert r.categoria == "reembolso"


def test_transferencia_propria_textual():
    r = _classifica("RESGATE POUPANCA MINHA POUPANCA")
    assert r.categoria == "transferencia_propria"
    assert r.patrimonio == "pessoa_fisica"


def test_pro_labore():
    r = _classifica("TRANSF PIX PRO LABORE TITULAR")
    assert r.categoria == "pessoal_prolabore"
    assert r.patrimonio == "ponte_pf_pj"
    assert r.needs_review is True


def test_tarifa_bancaria():
    r = _classifica("TARIFA MANUTENCAO PACOTE CONTA")
    assert r.categoria == "taxas_tarifas"


def test_iof():
    r = _classifica("IOF RESGATE POUPANCA")
    assert r.categoria == "taxas_tarifas"


def test_posto_combustivel():
    r = _classifica("POSTO IPIRANGA COMBUSTIVEL")
    assert r.categoria == "custo_operacional"
    assert r.proposito == "gasto_negocio"


def test_posto_em_conta_pessoal_vira_gasto_pessoal():
    r = _classifica("POSTO IPIRANGA COMBUSTIVEL", ctx=_ctx(tipo_conta="pessoal"))
    assert r.categoria == "custo_operacional"
    assert r.proposito == "gasto_pessoal"


def test_venda_balcao():
    r = _classifica("VENDA BALCAO PIX")
    assert r.categoria == "receita_venda"
    assert r.tratamento_tributario == "faturamento_pj"


def test_servico_pj():
    r = _classifica("CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA")
    assert r.categoria == "receita_servico"
    assert r.patrimonio == "atividade_negocio"


@pytest.mark.parametrize("desc", [
    "PIX RECEBIDO JOAO",
    "PIX RECEBIDO MARCOS SOUZA",
    "DEPOSITO EM CONTA",
    "TRANSFERENCIA RECEBIDA",
    "CREDITO EM CONTA",
])
def test_entrada_generica_vira_outros_com_review(desc):
    r = _classifica(desc, valor=650.0)
    assert r.categoria == "outros"
    assert r.needs_review is True
    assert r.proposito == "outros_indeterminado"
    assert r.confianca <= 0.5


def test_personal_rule_vence_heuristica():
    ctx = _ctx(personal_rules={"UBER": "custo_operacional"})
    r = _classifica("UBER TRIP 123", ctx=ctx)
    assert r.categoria == "custo_operacional"
    assert r.via == "regra_personalizada"


def test_personal_rule_com_categoria_invalida_eh_ignorada():
    ctx = _ctx(personal_rules={"DAS": "categoria_que_nao_existe"})
    r = _classifica("PAGTO GUIA DAS SIMPLES", ctx=ctx)
    assert r.categoria == "imposto_das"
    assert r.via == "heuristica"


def test_personal_rule_case_e_acento_insensiveis():
    ctx = _ctx(personal_rules={"padaria do zé": "custo_operacional"})
    r = _classifica("PADARIA DO ZE - COMPRA", ctx=ctx)
    assert r.categoria == "custo_operacional"
    assert r.via == "regra_personalizada"


@pytest.mark.parametrize("desc", [
    "PIX RECEBIDO JOAO",
    "PAGTO GUIA DAS SIMPLES",
    "PRO LABORE TITULAR",
    "POSTO IPIRANGA",
])
def test_determinismo(desc):
    assert _classifica(desc) == _classifica(desc)


def test_proposito_emitido_esta_no_literal():
    validos = set(get_args(PropositoId))
    for desc in ["PIX RECEBIDO JOAO", "PAGTO DAS SIMPLES", "PRO LABORE",
                 "ESTORNO UBER", "POSTO SHELL", "VENDA BALCAO"]:
        r = _classifica(desc)
        assert r.proposito in validos, f"{desc} -> {r.proposito}"
