"""M4_CONTRATO 14 — metricas A-D do classificador."""
from pathlib import Path

from caixaclaro.eval.runner import avaliar, carregar_dataset, imprimir

GOLDEN = Path(__file__).parent / "golden" / "dataset_v1.json"
B_MIN = 0.85
C_MIN = 0.10
C_MAX = 0.25


def test_dataset_carrega():
    casos = carregar_dataset(GOLDEN)
    assert len(casos) >= 20
    ids = [c["id"] for c in casos]
    assert len(ids) == len(set(ids))


def test_metrica_A_zero_violacoes():
    m = avaliar(carregar_dataset(GOLDEN))
    if m.A != 0: imprimir(m)
    assert m.A == 0


def test_metrica_B_acuracia_minima():
    m = avaliar(carregar_dataset(GOLDEN))
    if m.B < B_MIN: imprimir(m)
    assert m.B >= B_MIN, f"acuracia {m.B:.3f} < {B_MIN}"


def test_metrica_C_abstencao_na_faixa():
    m = avaliar(carregar_dataset(GOLDEN))
    if not (C_MIN <= m.C <= C_MAX): imprimir(m)
    assert C_MIN <= m.C <= C_MAX, f"abstencao {m.C:.3f} fora de {C_MIN}..{C_MAX}"


def test_metrica_D_zero_erros_criticos():
    m = avaliar(carregar_dataset(GOLDEN))
    if m.D != 0: imprimir(m)
    assert m.D == 0
