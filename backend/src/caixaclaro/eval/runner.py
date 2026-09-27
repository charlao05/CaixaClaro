"""Runner de eval — M4_CONTRATO §12 + §14 + §18.

Entradas:

  carregar_dataset(caminho) -> dict
      Carrega o envelope {taxonomia_version, criado_em, casos}.
      Array puro NAO e aceito — levanta ValueError.

  avaliar(casos) -> Metricas
      Coleta pura. Levanta ValueError se |C| < DATASET_MIN.

  avaliar_com_gates(dataset, *, schema) -> Metricas
      Valida o envelope contra schema (jsonschema), compara
      dataset.taxonomia_version com TAXONOMIA_VERSION, e roda os
      gates §18. Levanta GateError no primeiro que falhar.

CLI:

  python -m caixaclaro.eval.runner
      Carrega tests/golden/*, executa, imprime relatorio.
      Exit code 0 (PASS) ou 1 (FAIL).
"""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import jsonschema

from ..domain.fiscal.classificacao import ContextoClassificacao, classificar_v2
from ..domain.fiscal.guardrails import aplicar_guardrail
from ..domain.fiscal.taxonomia import TAXONOMIA_VERSION
from ..domain.fiscal.triagem import triar

RECEITAS = ("receita_servico", "receita_venda")
PALAVRAS_NUNCA_RECEITA = (
    "estorno", "devolucao", "reembolso", "ressarcimento",
    "emprestimo", "financiamento",
)

# §14 — pares (esperado, predito) que sao erro CRITICO.
# GRAVE e RELEVANTE alertam, nao reprovam.
CONJUNTO_CRITICO = frozenset({
    ("transferencia_propria", "receita_servico"),
    ("transferencia_propria", "receita_venda"),
    ("emprestimo", "receita_servico"),
    ("emprestimo", "receita_venda"),
    ("imposto_das", "pessoal_prolabore"),
    ("imposto_das", "outros"),
})

DIFFICULTIES = ("easy", "medium", "hard", "adversarial")
TAXONOMIA_ESPERADA = "v1"
DATASET_MIN = 15
B_MIN = 0.85
C_MIN = 0.10
C_MAX = 0.25


class GateError(Exception):
    """Um gate contratual de §18 falhou."""


@dataclass(frozen=True)
class CasoResultado:
    id: str
    difficulty: str
    esperado: str
    atual: str
    needs_review: bool
    guardrail_regra: str | None
    violacao: bool
    erro_critico: bool


@dataclass(frozen=True)
class Metricas:
    total: int
    violacoes: int
    acertos_avaliaveis: int
    avaliaveis: int
    abstratidos: int
    erros_criticos: int
    por_dificuldade: dict
    casos: list[CasoResultado] = field(default_factory=list)

    @property
    def A(self) -> int:
        """Métrica A (§13) — violações NUNCA. Gate: == 0."""
        return self.violacoes

    @property
    def B(self) -> float:
        return self.acertos_avaliaveis / self.avaliaveis if self.avaliaveis else 0.0

    @property
    def C(self) -> float:
        return self.abstratidos / self.total if self.total else 0.0

    @property
    def D(self) -> int:
        return self.erros_criticos


def carregar_dataset(caminho):
    """Carrega envelope §12. Recusa array puro."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise ValueError(
            "dataset deve ser envelope {taxonomia_version, criado_em, casos}; "
            f"recebido: {type(dados).__name__}"
        )
    return dados


def carregar_schema(caminho):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def avaliar(casos):
    """Coleta pura. Levanta ValueError se |C| < DATASET_MIN."""
    if len(casos) < DATASET_MIN:
        raise ValueError(f"dataset tem {len(casos)}, minimo {DATASET_MIN}")

    ctx = ContextoClassificacao(personal_rules={})
    resultados = []
    violacoes = acertos_avaliaveis = avaliaveis = abstratidos = erros_criticos = 0
    por_dif = defaultdict(lambda: {"total": 0, "abst": 0, "acertos": 0})

    for caso in casos:
        desc = caso["descricao"]
        valor = Decimal(str(caso["valor"]))
        esperado = caso["categoria_esperada"]
        dif = caso["difficulty"]

        classif = classificar_v2(desc, valor, ctx)
        guard = aplicar_guardrail(
            classif, descricao=desc,
            cpf_titular_hash=caso.get("cpf_titular_hash"),
            cpf_contraparte_hash=caso.get("cpf_contraparte_hash"),
        )
        tri = triar(classif, guard)

        atual = guard.categoria_corrigida
        norm = desc.lower()

        violacao = (
            any(p in norm for p in PALAVRAS_NUNCA_RECEITA)
            and atual in RECEITAS
        )
        erro_critico = (
            not tri.needs_review
            and (esperado, atual) in CONJUNTO_CRITICO
        )

        if violacao: violacoes += 1
        if erro_critico: erros_criticos += 1

        por_dif[dif]["total"] += 1
        if tri.needs_review:
            abstratidos += 1
            por_dif[dif]["abst"] += 1
        else:
            avaliaveis += 1
            if atual == esperado:
                acertos_avaliaveis += 1
                por_dif[dif]["acertos"] += 1

        resultados.append(CasoResultado(
            id=caso["id"], difficulty=dif, esperado=esperado, atual=atual,
            needs_review=tri.needs_review,
            guardrail_regra=guard.regra_acionada,
            violacao=violacao, erro_critico=erro_critico,
        ))

    return Metricas(
        total=len(casos), violacoes=violacoes,
        acertos_avaliaveis=acertos_avaliaveis, avaliaveis=avaliaveis,
        abstratidos=abstratidos, erros_criticos=erros_criticos,
        por_dificuldade=dict(por_dif), casos=resultados,
    )


def imprimir(m):
    print()
    print(f"{'id':5} {'dif':5} {'esperado':22} {'atual':22} {'nr':3} {'viola':5} {'crit':4}")
    print("-" * 76)
    for c in m.casos:
        print(f"{c.id:5} {c.difficulty:5} {c.esperado:22} {c.atual:22} "
              f"{'S' if c.needs_review else '.':3} "
              f"{'V' if c.violacao else '.':5} "
              f"{'E' if c.erro_critico else '.':4}")
    print()
    print(f"total={m.total} |A|={m.avaliaveis} abstratidos={m.abstratidos}")
    print(f"Metrica A (violacoes NUNCA) = {m.A} (esperado 0)")
    print(f"B acuracia                  = {m.B:.3f} (esperado >= 0.850)")
    print(f"C abstencao                 = {m.C:.3f} (esperado 0.10..0.25)")
    print(f"D erros criticos            = {m.D} (esperado 0)")
    print()
    print("Breakdown por difficulty:")
    for dif in DIFFICULTIES:
        d = m.por_dificuldade.get(dif)
        if not d:
            continue
        print(f"  {dif:12} total={d['total']:2} abst={d['abst']:2} acertos={d['acertos']}")
    print()


def taxonomia_ok() -> bool:
    return TAXONOMIA_VERSION == TAXONOMIA_ESPERADA


def avaliar_com_gates(dataset, *, schema):
    """Verifica §18. Levanta GateError no primeiro gate que falhar.

    dataset: envelope {taxonomia_version, criado_em, casos}
    schema:  JSON Schema do envelope
    """
    try:
        jsonschema.validate(dataset, schema)
    except jsonschema.ValidationError as e:
        raise GateError(f"schema invalido: {e.message}") from e

    taxonomia_ds = dataset.get("taxonomia_version")
    if taxonomia_ds != TAXONOMIA_ESPERADA:
        raise GateError(
            f"taxonomia_version do dataset = {taxonomia_ds!r} "
            f"!= {TAXONOMIA_ESPERADA!r}"
        )

    if not taxonomia_ok():
        raise GateError(f"TAXONOMIA_VERSION (codigo) != {TAXONOMIA_ESPERADA!r}")

    m = avaliar(dataset["casos"])

    if m.avaliaveis < DATASET_MIN:
        raise GateError(
            f"|A| = {m.avaliaveis} < {DATASET_MIN} (avaliaveis insuficientes)"
        )
    if m.violacoes > 0:
        raise GateError(f"Metrica A (violacoes NUNCA) = {m.violacoes} > 0")
    if m.B < B_MIN:
        raise GateError(f"Metrica B = {m.B:.3f} < {B_MIN}")
    if not (C_MIN <= m.C <= C_MAX):
        raise GateError(f"Metrica C = {m.C:.3f} fora de [{C_MIN}, {C_MAX}]")
    for dif in ("easy", "medium"):
        d = m.por_dificuldade.get(dif, {})
        if d.get("abst", 0) > 0:
            raise GateError(f"abstencao em {dif} = {d['abst']} > 0")
    if m.D > 0:
        raise GateError(f"Metrica D = {m.D} (erros criticos) > 0")

    return m


def _cli() -> int:
    import argparse
    import os
    import sys
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(prog="caixaclaro.eval.runner")
    parser.add_argument(
        "--publicar",
        metavar="CAMINHO",
        default=None,
        help="Se dado e o eval passar, grava envelope JSON neste caminho.",
    )
    args = parser.parse_args()

    backend = Path(__file__).resolve().parents[3]
    golden = backend / "tests" / "golden"

    try:
        dataset = carregar_dataset(golden / "dataset_v1.json")
        schema = carregar_schema(golden / "schema.json")
    except (FileNotFoundError, ValueError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    try:
        m = avaliar_com_gates(dataset, schema=schema)
    except GateError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    imprimir(m)
    print("PASS")

    if args.publicar:
        _publicar(
            m,
            Path(args.publicar),
            executado_em=datetime.now(timezone.utc).isoformat(),
        )

    return 0


def _publicar(m, destino: Path, *, executado_em: str) -> None:
    """Grava envelope de M9.3_DECISAO em disco. Chamado apenas em PASS.

    Em FAIL nao ha publicacao: 'ultima execucao' aqui significa
    'ultima execucao bem-sucedida'.
    """
    import json
    import os

    destino.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "executado_em": executado_em,
        "commit": os.environ.get("GITHUB_SHA", "local"),
        "taxonomia_version": TAXONOMIA_VERSION,
        "total": m.total,
        "avaliaveis": m.avaliaveis,
        "abstratidos": m.abstratidos,
        "metricas": {"A": m.A, "B": round(m.B, 3), "C": round(m.C, 3), "D": m.D},
        "por_dificuldade": m.por_dificuldade,
        "resultado": "PASS",
    }
    destino.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys
    sys.exit(_cli())
