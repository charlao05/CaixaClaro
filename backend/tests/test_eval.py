"""M4_CONTRATO §14 + §18 — metricas + validacoes contratuais."""
from pathlib import Path

from caixaclaro.eval.runner import (
    avaliar, carregar_dataset, carregar_schema, imprimir, taxonomia_ok,
    DATASET_MIN,
)

GOLDEN = Path(__file__).parent / "golden" / "dataset_v1.json"
SCHEMA = Path(__file__).parent / "golden" / "schema.json"
B_MIN = 0.85
C_MIN = 0.10
C_MAX = 0.25


def test_schema_do_dataset():
    casos = carregar_dataset(GOLDEN)
    schema = carregar_schema(SCHEMA)
    from caixaclaro.eval.runner import _validar_schema
    _validar_schema(casos, schema)


def test_taxonomia_version_v1():
    assert taxonomia_ok(), "TAXONOMIA_VERSION deve ser v1"


def test_dataset_tem_minimo():
    casos = carregar_dataset(GOLDEN)
    assert len(casos) >= DATASET_MIN


def test_dataset_cobre_todas_dificuldades():
    casos = carregar_dataset(GOLDEN)
    dificuldades = {c["difficulty"] for c in casos}
    assert dificuldades == {"easy", "medium", "hard", "adversarial"}


def test_cada_regra_nunca_tem_ao_menos_um_caso():
    casos = carregar_dataset(GOLDEN)
    regras_presentes = {c.get("regra") for c in casos if c.get("regra")}
    # §6 guardrails: cpf_proprio, emprestimo, estorno, ponte_pf_pj, tributo
    esperadas = {"cpf_proprio", "emprestimo", "estorno", "ponte_pf_pj", "tributo"}
    faltando = esperadas - regras_presentes
    assert not faltando, f"regras NUNCA sem caso: {faltando}"


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
    assert C_MIN <= m.C <= C_MAX, f"abstencao {m.C:.3f}"


def test_sem_abstencao_em_easy_medium():
    m = avaliar(carregar_dataset(GOLDEN))
    problemas = []
    for dif in ("easy", "medium"):
        d = m.por_dificuldade.get(dif, {})
        if d.get("abst", 0) > 0:
            problemas.append(f"{dif}={d['abst']}")
    if problemas: imprimir(m)
    assert not problemas, f"abstencao em {problemas}"


def test_metrica_D_zero_erros_criticos():
    m = avaliar(carregar_dataset(GOLDEN))
    if m.D != 0: imprimir(m)
    assert m.D == 0
