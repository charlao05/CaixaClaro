"""§19.3 — test_classificacao_contrato.

Para cada descricao, valida os 9 campos de §4 com tipos corretos e
bounds. O contrato fala "para cada chamada" — nao so uma.
"""
from decimal import Decimal

import pytest

from caixaclaro.domain.fiscal.classificacao import (
    ContextoClassificacao,
    classificar_v2,
)

CASOS = [
    "PAGTO GUIA DAS SIMPLES",
    "DARF CARNE LEAO",
    "PGMEI PARCELA 1",
    "CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA",
    "PIX RECEBIDO SERVICO PRESTADO LTDA",
    "SERVICO PRESTADO A EMPRESA XYZ LTDA",
    "VENDA BALCAO CARTAO",
    "VENDA SHOPEE REPASSE",
    "CREDITO TED FOLHA SALARIO",
    "SALARIO MENSAL EMPRESA ABC",
    "BENEFICIO INSS",
    "TARIFA BANCARIA MENSAL",
    "IOF RESGATE POUPANCA",
    "POSTO IPIRANGA COMBUSTIVEL",
    "INTERNET VIVO FIBRA",
    "TRANSF PRO LABORE TITULAR",
    "RETIRADA TITULAR",
    "ESTORNO COMPRA CANCELADA",
    "DEVOLUCAO PIX RECEBIDA",
    "CREDITO EMPRESTIMO CONSIGNADO BCO",
    "FINANCIAMENTO VEICULO PARCELA",
    "PIX RECEBIDO JOAO",
    "DEPOSITO EM CONTA",
    "TRANSFERENCIA RECEBIDA",
]


@pytest.mark.parametrize("descricao", CASOS)
def test_classificacao_contrato_nove_campos(descricao):
    ctx = ContextoClassificacao(personal_rules={})
    r = classificar_v2(descricao, Decimal("100.00"), ctx)

    assert isinstance(r.categoria, str) and r.categoria
    assert isinstance(r.proposito, str) and r.proposito
    assert isinstance(r.origem_sugerida, str) and r.origem_sugerida
    assert isinstance(r.patrimonio, str) and r.patrimonio
    assert isinstance(r.tratamento_tributario, str) and r.tratamento_tributario
    assert isinstance(r.confianca, (int, float))
    assert 0.0 <= float(r.confianca) <= 1.0
    assert isinstance(r.needs_review, bool)
    assert r.via in ("regra_personalizada", "heuristica")
    assert r.motivo is None or isinstance(r.motivo, str)
