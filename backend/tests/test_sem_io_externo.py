"""§19.14 — sem I/O externo no caminho do classificador.

Prova por execucao (nao por inspecao estatica de imports) que o
pipeline classificar_v2 -> guardrail -> triagem nao toca banco,
HTTP nem LLM.
"""
from decimal import Decimal

import pytest

import caixaclaro.db as db_mod
from caixaclaro.domain.fiscal.classificacao import (
    ContextoClassificacao,
    classificar_v2,
)
from caixaclaro.domain.fiscal.guardrails import aplicar_guardrail
from caixaclaro.domain.fiscal.triagem import triar


def _proibe(*args, **kw):
    raise RuntimeError("I/O externo detectado no caminho do classificador")


CASOS = [
    "PAGTO GUIA DAS SIMPLES",
    "CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA",
    "PIX RECEBIDO JOAO",
    "TRANSF PRO LABORE TITULAR",
    "CREDITO EMPRESTIMO CONSIGNADO BCO",
    "ESTORNO COMPRA CANCELADA",
    "POSTO IPIRANGA COMBUSTIVEL",
    "TARIFA BANCARIA MENSAL",
]


@pytest.mark.parametrize("descricao", CASOS)
def test_classificador_sem_io_externo(descricao, monkeypatch):
    # 1. Bloqueia a funcao de conexao do projeto.
    monkeypatch.setattr(db_mod, "conexao", _proibe)

    # 2. Bloqueia HTTP top-level do httpx (fixtures usam AsyncClient,
    #    nao essas funcoes; elas so seriam usadas por chamada direta).
    import httpx
    for nome in ("get", "post", "request", "put", "delete", "patch", "head"):
        if hasattr(httpx, nome):
            monkeypatch.setattr(httpx, nome, _proibe, raising=False)

    # 3. requests, se instalado.
    try:
        import requests
        for nome in ("get", "post", "request", "put", "delete", "patch", "head"):
            if hasattr(requests, nome):
                monkeypatch.setattr(requests, nome, _proibe, raising=False)
    except ImportError:
        pass

    # Pipeline completo. Se qualquer I/O for disparado, RuntimeError
    # estoura e o teste falha.
    ctx = ContextoClassificacao(personal_rules={})
    classif = classificar_v2(descricao, Decimal("100.00"), ctx)
    guard = aplicar_guardrail(classif, descricao=descricao)
    tri = triar(classif, guard)

    # Sanidade minima.
    assert classif.categoria
    assert isinstance(tri.needs_review, bool)
