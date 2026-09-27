"""Gates §18 — testados isoladamente do dataset golden."""
from pathlib import Path

import pytest

from caixaclaro.eval import runner as r
from caixaclaro.eval.runner import (
    CONJUNTO_CRITICO,
    GateError,
    Metricas,
    avaliar,
    avaliar_com_gates,
    carregar_schema,
)

SCHEMA = Path(__file__).parent / "golden" / "schema.json"
SCHEMA_OBJ = carregar_schema(SCHEMA)


def _caso(i, desc, cat, diff="easy", esp=None):
    return {
        "id": f"t{i:03d}",
        "descricao": desc,
        "valor": "100.00",
        "categoria_esperada": esp or cat,
        "difficulty": diff,
    }


def _dataset_minimo(n=20):
    return [
        _caso(i, "PAGTO GUIA DAS SIMPLES", "imposto_das", diff="easy")
        for i in range(n)
    ]


def _envelope(casos, *, taxonomia_version="v1", criado_em="2026-09-27"):
    return {
        "taxonomia_version": taxonomia_version,
        "criado_em": criado_em,
        "casos": casos,
    }


def _metricas(**overrides):
    base = dict(
        total=20, violacoes=0, acertos_avaliaveis=20, avaliaveis=20,
        abstratidos=0, erros_criticos=0,
        por_dificuldade={"easy": {"total": 20, "abst": 0, "acertos": 20}},
        casos=[],
    )
    base.update(overrides)
    return Metricas(**base)


def _gate(casos, **kw):
    return avaliar_com_gates(_envelope(casos), schema=SCHEMA_OBJ, **kw)


# ============================================================
# Gate 0 — schema
# ============================================================

def test_gate_valida_schema_caso_com_campo_extra():
    casos = _dataset_minimo()
    casos[0]["campo_extra"] = "x"
    with pytest.raises(GateError, match="schema invalido"):
        avaliar_com_gates(_envelope(casos), schema=SCHEMA_OBJ)


def test_gate_valida_schema_envelope_sem_taxonomia():
    casos = _dataset_minimo()
    env = {"criado_em": "2026-09-27", "casos": casos}
    with pytest.raises(GateError, match="schema invalido"):
        avaliar_com_gates(env, schema=SCHEMA_OBJ)


# ============================================================
# Gate 1 — taxonomia (dataset e codigo)
# ============================================================

def test_gate_recusa_taxonomia_dataset_divergente():
    env = _envelope(_dataset_minimo(), taxonomia_version="v2")
    with pytest.raises(GateError, match="taxonomia_version"):
        avaliar_com_gates(env, schema=SCHEMA_OBJ)


def test_gate_recusa_taxonomia_codigo_divergente(monkeypatch):
    monkeypatch.setattr(r, "taxonomia_ok", lambda: False)
    with pytest.raises(GateError, match="TAXONOMIA_VERSION"):
        _gate(_dataset_minimo())


# ============================================================
# Gate 2 — |A| >= DATASET_MIN
# ============================================================

def test_gate_recusa_avaliaveis_insuficientes():
    casos = _dataset_minimo(n=20)
    for i in range(6):
        casos[i] = _caso(i, "PIX RECEBIDO JOAO", "outros", diff="hard")
    with pytest.raises(GateError, match="avaliaveis"):
        _gate(casos)


# ============================================================
# Gates 3-7 — via monkeypatch
# ============================================================

def test_gate_A_positivo(monkeypatch):
    monkeypatch.setattr(r, "avaliar", lambda c: _metricas(violacoes=1))
    with pytest.raises(GateError, match="Metrica A"):
        _gate(_dataset_minimo())


def test_gate_B_abaixo_de_085(monkeypatch):
    monkeypatch.setattr(
        r, "avaliar",
        lambda c: _metricas(acertos_avaliaveis=15, avaliaveis=20),
    )
    with pytest.raises(GateError, match="Metrica B"):
        _gate(_dataset_minimo())


def test_gate_C_abaixo_da_faixa(monkeypatch):
    monkeypatch.setattr(
        r, "avaliar", lambda c: _metricas(abstratidos=0, total=20),
    )
    with pytest.raises(GateError, match="Metrica C"):
        _gate(_dataset_minimo())


def test_gate_C_acima_da_faixa(monkeypatch):
    monkeypatch.setattr(
        r, "avaliar", lambda c: _metricas(abstratidos=10, total=20),
    )
    with pytest.raises(GateError, match="Metrica C"):
        _gate(_dataset_minimo())


def test_gate_abstencao_em_easy(monkeypatch):
    monkeypatch.setattr(
        r, "avaliar",
        lambda c: _metricas(
            abstratidos=3, total=20,
            por_dificuldade={
                "easy": {"total": 10, "abst": 1, "acertos": 9},
                "hard": {"total": 10, "abst": 2, "acertos": 8},
            },
        ),
    )
    with pytest.raises(GateError, match="abstencao em easy"):
        _gate(_dataset_minimo())


def test_gate_abstencao_em_medium(monkeypatch):
    monkeypatch.setattr(
        r, "avaliar",
        lambda c: _metricas(
            abstratidos=3, total=20,
            por_dificuldade={
                "easy": {"total": 10, "abst": 0, "acertos": 10},
                "medium": {"total": 5, "abst": 1, "acertos": 4},
                "hard": {"total": 5, "abst": 2, "acertos": 3},
            },
        ),
    )
    with pytest.raises(GateError, match="abstencao em medium"):
        _gate(_dataset_minimo())


def test_gate_D_positivo(monkeypatch):
    monkeypatch.setattr(
        r, "avaliar",
        lambda c: _metricas(
            abstratidos=4, total=20,
            acertos_avaliaveis=15, avaliaveis=16,
            erros_criticos=1,
            por_dificuldade={
                "easy": {"total": 10, "abst": 0, "acertos": 10},
                "hard": {"total": 10, "abst": 4, "acertos": 5},
            },
        ),
    )
    with pytest.raises(GateError, match="Metrica D"):
        _gate(_dataset_minimo())


# ============================================================
# CONJUNTO_CRITICO
# ============================================================

def test_conjunto_critico_contem_pares_do_contrato():
    assert ("transferencia_propria", "receita_servico") in CONJUNTO_CRITICO
    assert ("transferencia_propria", "receita_venda") in CONJUNTO_CRITICO
    assert ("emprestimo", "receita_servico") in CONJUNTO_CRITICO
    assert ("emprestimo", "receita_venda") in CONJUNTO_CRITICO
    assert ("imposto_das", "pessoal_prolabore") in CONJUNTO_CRITICO
    assert ("imposto_das", "outros") in CONJUNTO_CRITICO


def test_conjunto_critico_exclui_grave_e_relevante():
    assert ("reembolso", "receita_servico") not in CONJUNTO_CRITICO
    assert ("reembolso", "receita_venda") not in CONJUNTO_CRITICO
    assert ("receita_servico", "reembolso") not in CONJUNTO_CRITICO


def test_D_detecta_par_critico_no_pipeline_real():
    casos = _dataset_minimo(n=20)
    casos.append(_caso(
        99,
        "CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA",
        "receita_servico",
        diff="hard",
        esp="transferencia_propria",
    ))
    m = avaliar(casos)
    assert m.D == 1


def test_D_nao_conta_abstido():
    casos = _dataset_minimo(n=20)
    casos.append(_caso(
        99,
        "PIX RECEBIDO JOAO",
        "outros",
        diff="adversarial",
        esp="imposto_das",
    ))
    m = avaliar(casos)
    assert m.D == 0
