"""Testes unitarios de security.erros - E1.

Travam o contrato do 'detail' e a extensao 'extra'.
"""
from caixaclaro.security.erros import erro


def test_erro_sem_extra_mantem_contrato_original():
    e = erro(402, "ACESSO_BLOQUEADO")
    assert e.status_code == 402
    assert e.detail == {
        "erro": "ACESSO_BLOQUEADO",
        "mensagem": "ACESSO_BLOQUEADO",
    }


def test_erro_com_mensagem_customizada_sem_extra():
    e = erro(402, "ACESSO_BLOQUEADO", "Assinatura expirada.")
    assert e.detail == {
        "erro": "ACESSO_BLOQUEADO",
        "mensagem": "Assinatura expirada.",
    }


def test_erro_com_extra_mescla_chaves():
    e = erro(
        402,
        "ACESSO_BLOQUEADO",
        "Assinatura expirada.",
        extra={"estado": "bloqueado", "assinatura_url": "/billing/checkout"},
    )
    assert e.detail == {
        "erro": "ACESSO_BLOQUEADO",
        "mensagem": "Assinatura expirada.",
        "estado": "bloqueado",
        "assinatura_url": "/billing/checkout",
    }


def test_erro_extra_nao_sobrescreve_erro_nem_mensagem():
    e = erro(
        402,
        "ACESSO_BLOQUEADO",
        "Assinatura expirada.",
        extra={"erro": "NAO_SOBRESCREVE", "mensagem": "NAO_SOBRESCREVE"},
    )
    assert e.detail["erro"] == "ACESSO_BLOQUEADO"
    assert e.detail["mensagem"] == "Assinatura expirada."


def test_erro_extra_vazio_e_equivalente_a_none():
    a = erro(402, "X", extra={})
    b = erro(402, "X", extra=None)
    assert a.detail == b.detail