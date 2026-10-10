"""Testes unitarios de services.autorizacao - E1.

Funcao pura. Sem HTTP. Sem DB.
"""
from datetime import datetime, timedelta, timezone

import pytest

from caixaclaro.config import settings
from caixaclaro.services.autorizacao import (
    ContextoAutorizacao,
    avaliar,
    decidir,
    fim_do_teste,
    situacao,
)


AGORA = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _ctx(*, trial_exempt=False, dias_desde_criacao=0, periodo_fim=None, agora=AGORA):
    return ContextoAutorizacao(
        trial_exempt=trial_exempt,
        criado_em=agora - timedelta(days=dias_desde_criacao),
        periodo_fim=periodo_fim,
        agora=agora,
    )


# ---- trial_exempt: excecao persistida ----

def test_trial_exempt_permite_mesmo_com_tudo_expirado():
    assert decidir(_ctx(trial_exempt=True, dias_desde_criacao=365)) is True


def test_trial_exempt_permite_mesmo_sem_periodo():
    assert decidir(_ctx(trial_exempt=True, dias_desde_criacao=365,
                        periodo_fim=None)) is True


# ---- trial vigente: fronteira estrita ----

def test_trial_vigente_no_primeiro_dia():
    assert decidir(_ctx(dias_desde_criacao=0)) is True


def test_trial_vigente_um_microssegundo_antes_do_fim():
    dias = settings().trial_dias
    criado = AGORA - timedelta(days=dias) + timedelta(microseconds=1)
    ctx = ContextoAutorizacao(
        trial_exempt=False, criado_em=criado, periodo_fim=None, agora=AGORA,
    )
    assert decidir(ctx) is True


def test_trial_bloqueia_na_fronteira_exata():
    """criado_em + trial_dias == agora -> bloqueado (comparacao estrita)."""
    dias = settings().trial_dias
    criado = AGORA - timedelta(days=dias)
    ctx = ContextoAutorizacao(
        trial_exempt=False, criado_em=criado, periodo_fim=None, agora=AGORA,
    )
    assert decidir(ctx) is False


def test_trial_bloqueia_um_segundo_depois_do_fim():
    dias = settings().trial_dias
    criado = AGORA - timedelta(days=dias, seconds=1)
    ctx = ContextoAutorizacao(
        trial_exempt=False, criado_em=criado, periodo_fim=None, agora=AGORA,
    )
    assert decidir(ctx) is False


# ---- periodo pago: fronteira estrita ----

def test_periodo_futuro_permite_com_trial_expirado():
    ctx = _ctx(
        dias_desde_criacao=365,
        periodo_fim=AGORA + timedelta(days=1),
    )
    assert decidir(ctx) is True


def test_periodo_passado_bloqueia_com_trial_expirado():
    ctx = _ctx(
        dias_desde_criacao=365,
        periodo_fim=AGORA - timedelta(seconds=1),
    )
    assert decidir(ctx) is False


def test_periodo_exato_bloqueia():
    """periodo_fim == agora -> bloqueado (comparacao estrita)."""
    ctx = _ctx(dias_desde_criacao=365, periodo_fim=AGORA)
    assert decidir(ctx) is False


def test_sem_periodo_e_sem_trial_bloqueia():
    assert decidir(_ctx(dias_desde_criacao=365, periodo_fim=None)) is False


# ---- 'status' nao e parametro do contexto ----

def test_contexto_nao_carrega_status():
    """Documenta o fato consolidado do billing.

    pausada + periodo_fim > agora   -> permitido
    pausada + periodo_fim <= agora  -> bloqueado

    Como 'pausada' nao e um campo do contexto, esses dois casos ja sao
    cobertos por test_periodo_futuro_permite_com_trial_expirado e
    test_periodo_passado_bloqueia_com_trial_expirado.
    """
    assert "status" not in ContextoAutorizacao.__dataclass_fields__
    assert "pausada_ate" not in ContextoAutorizacao.__dataclass_fields__


# ---- 'agora' default None usa o relogio real ----

def test_agora_default_usa_agora_real():
    ctx = ContextoAutorizacao(
        trial_exempt=False,
        criado_em=datetime.now(timezone.utc) - timedelta(days=365),
        periodo_fim=None,
        agora=None,
    )
    assert decidir(ctx) is False


# ---- determinismo ----

def test_mesmo_contexto_mesma_decisao():
    ctx = _ctx(dias_desde_criacao=365, periodo_fim=AGORA + timedelta(days=1))
    assert decidir(ctx) is decidir(ctx)

# ---- E2: avaliar() e motivo do bloqueio ----

def test_avaliar_trial_exempt_permite_sem_motivo():
    d = avaliar(_ctx(trial_exempt=True, dias_desde_criacao=365))
    assert d.permitido is True
    assert d.motivo is None


def test_avaliar_trial_vigente_sem_motivo():
    d = avaliar(_ctx(dias_desde_criacao=0))
    assert d.permitido is True
    assert d.motivo is None


def test_avaliar_periodo_futuro_sem_motivo():
    d = avaliar(_ctx(dias_desde_criacao=365,
                     periodo_fim=AGORA + timedelta(days=1)))
    assert d.permitido is True
    assert d.motivo is None


def test_avaliar_trial_expirado_sem_subscription():
    d = avaliar(_ctx(dias_desde_criacao=30, periodo_fim=None))
    assert d.permitido is False
    assert d.motivo == "trial_expirado"


def test_avaliar_assinatura_vencida():
    d = avaliar(_ctx(dias_desde_criacao=30,
                     periodo_fim=AGORA - timedelta(seconds=1)))
    assert d.permitido is False
    assert d.motivo == "assinatura_expirada"


def test_avaliar_assinatura_vencida_com_trial_vigente_permitido():
    """Precedencia do motivo so e' relevante se permitido=False."""
    d = avaliar(_ctx(dias_desde_criacao=0,
                     periodo_fim=AGORA - timedelta(days=1)))
    assert d.permitido is True
    assert d.motivo is None


def test_avaliar_periodo_exato_motivo_assinatura_expirada():
    """periodo_fim == agora -> bloqueado com motivo de assinatura."""
    d = avaliar(_ctx(dias_desde_criacao=30, periodo_fim=AGORA))
    assert d.permitido is False
    assert d.motivo == "assinatura_expirada"


def test_avaliar_determinismo():
    ctx = _ctx(dias_desde_criacao=30, periodo_fim=None)
    d1 = avaliar(ctx)
    d2 = avaliar(ctx)
    assert d1 == d2


# ---- situacao(): de onde vem o acesso (revisão de 2026-10-09, achado R8) ----

def test_situacao_cobre_os_cinco_casos():
    futuro = AGORA + timedelta(days=10)
    passado = AGORA - timedelta(days=1)
    assert situacao(_ctx(trial_exempt=True, dias_desde_criacao=365)) == "isento"
    assert situacao(_ctx(dias_desde_criacao=1)) == "teste"
    assert situacao(_ctx(dias_desde_criacao=40, periodo_fim=futuro)) == "assinatura"
    assert situacao(_ctx(dias_desde_criacao=40, periodo_fim=passado)) == "assinatura_expirada"
    assert situacao(_ctx(dias_desde_criacao=40)) == "trial_expirado"


def test_situacao_e_avaliar_nunca_discordam():
    futuro = AGORA + timedelta(days=10)
    passado = AGORA - timedelta(days=1)
    for ctx in (
        _ctx(trial_exempt=True, dias_desde_criacao=365),
        _ctx(dias_desde_criacao=0),
        _ctx(dias_desde_criacao=1, periodo_fim=passado),
        _ctx(dias_desde_criacao=40, periodo_fim=futuro),
        _ctx(dias_desde_criacao=40, periodo_fim=passado),
        _ctx(dias_desde_criacao=40, periodo_fim=AGORA),
        _ctx(dias_desde_criacao=40),
    ):
        decisao = avaliar(ctx)
        s = situacao(ctx)
        assert decisao.permitido == (s in ("isento", "teste", "assinatura"))
        assert decisao.motivo == (None if decisao.permitido else s)


def test_fim_do_teste_soma_os_dias_configurados():
    criado = AGORA - timedelta(days=3)
    assert fim_do_teste(criado) == criado + timedelta(days=settings().trial_dias)
