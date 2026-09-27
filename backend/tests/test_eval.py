"""M4_CONTRATO §12 + §14 + §18 — metricas + validacoes contratuais."""
from pathlib import Path

import jsonschema
import pytest

from caixaclaro.eval.runner import (
    DATASET_MIN,
    avaliar,
    carregar_dataset,
    carregar_schema,
    imprimir,
    taxonomia_ok,
)

GOLDEN = Path(__file__).parent / "golden" / "dataset_v1.json"
SCHEMA = Path(__file__).parent / "golden" / "schema.json"
B_MIN = 0.85
C_MIN = 0.10
C_MAX = 0.25


def _casos():
    return carregar_dataset(GOLDEN)["casos"]


def test_schema_do_dataset():
    envelope = carregar_dataset(GOLDEN)
    schema = carregar_schema(SCHEMA)
    jsonschema.validate(envelope, schema)


def test_taxonomia_version_v1():
    assert taxonomia_ok(), "TAXONOMIA_VERSION do codigo deve ser v1"
    envelope = carregar_dataset(GOLDEN)
    assert envelope["taxonomia_version"] == "v1"


def test_dataset_tem_minimo():
    assert len(_casos()) >= DATASET_MIN


def test_dataset_cobre_todas_dificuldades():
    dificuldades = {c["difficulty"] for c in _casos()}
    assert dificuldades == {"easy", "medium", "hard", "adversarial"}


def test_cada_regra_nunca_tem_ao_menos_um_caso():
    regras = {c.get("regra") for c in _casos() if c.get("regra")}
    esperadas = {"cpf_proprio", "emprestimo", "estorno", "ponte_pf_pj", "tributo"}
    faltando = esperadas - regras
    assert not faltando, f"regras NUNCA sem caso: {faltando}"


def test_metrica_A_zero_violacoes():
    m = avaliar(_casos())
    if m.violacoes != 0: imprimir(m)
    assert m.violacoes == 0


def test_metrica_B_acuracia_minima():
    m = avaliar(_casos())
    if m.B < B_MIN: imprimir(m)
    assert m.B >= B_MIN


def test_metrica_C_abstencao_na_faixa():
    m = avaliar(_casos())
    if not (C_MIN <= m.C <= C_MAX): imprimir(m)
    assert C_MIN <= m.C <= C_MAX


def test_sem_abstencao_em_easy_medium():
    m = avaliar(_casos())
    problemas = []
    for dif in ("easy", "medium"):
        d = m.por_dificuldade.get(dif, {})
        if d.get("abst", 0) > 0:
            problemas.append(f"{dif}={d['abst']}")
    if problemas: imprimir(m)
    assert not problemas


def test_metrica_D_zero_erros_criticos():
    m = avaliar(_casos())
    if m.D != 0: imprimir(m)
    assert m.D == 0


def test_avaliar_recusa_dataset_pequeno():
    casos = [
        {"id": f"x{i:03d}", "descricao": "PIX RECEBIDO", "valor": "1.00",
         "categoria_esperada": "outros", "difficulty": "easy"}
        for i in range(DATASET_MIN - 1)
    ]
    with pytest.raises(ValueError):
        avaliar(casos)


def test_avaliar_aceita_dataset_no_minimo():
    casos = [
        {"id": f"y{i:03d}", "descricao": "PAGTO GUIA DAS SIMPLES",
         "valor": "1.00", "categoria_esperada": "imposto_das",
         "difficulty": "easy"}
        for i in range(DATASET_MIN)
    ]
    m = avaliar(casos)
    assert m.total == DATASET_MIN


def test_carregar_dataset_recusa_array_puro(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="envelope"):
        carregar_dataset(p)
