"""Runner de eval — M4_CONTRATO §14 + §18."""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

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


def _validar_schema(casos, schema):
    req = set(schema["items"]["required"])
    props = set(schema["items"]["properties"].keys())
    enum_dif = set(schema["items"]["properties"]["difficulty"]["enum"])
    ids_vistos = set()
    for i, c in enumerate(casos):
        faltando = req - set(c.keys())
        if faltando:
            raise ValueError(f"caso #{i} ({c.get('id')}) faltando: {faltando}")
        extras = set(c.keys()) - props
        if extras:
            raise ValueError(f"caso #{i} ({c.get('id')}) campos extras: {extras}")
        if c["difficulty"] not in enum_dif:
            raise ValueError(f"caso {c['id']} difficulty invalida: {c['difficulty']}")
        if c["id"] in ids_vistos:
            raise ValueError(f"id duplicado: {c['id']}")
        ids_vistos.add(c["id"])


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
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def carregar_schema(caminho):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def avaliar(casos):
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
        # §14 — apenas pares do CONJUNTO_CRITICO; abstidos nao entram.
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
    print(f"total={m.total} avaliaveis={m.avaliaveis} abstratidos={m.abstratidos}")
    print(f"A violacoes      = {m.A} (esperado 0)")
    print(f"B acuracia       = {m.B:.3f} (esperado >= 0.850)")
    print(f"C abstencao      = {m.C:.3f} (esperado 0.10..0.25)")
    print(f"D erros criticos = {m.D} (esperado 0)")
    print()


def taxonomia_ok() -> bool:
    return TAXONOMIA_VERSION == TAXONOMIA_ESPERADA


def avaliar_com_gates(casos, schema=None):
    """Verifica §18. Levanta GateError no primeiro gate que falhar."""
    if schema is not None:
        _validar_schema(casos, schema)

    if not taxonomia_ok():
        raise GateError(f"TAXONOMIA_VERSION != {TAXONOMIA_ESPERADA!r}")

    m = avaliar(casos)

    if m.avaliaveis < DATASET_MIN:
        raise GateError(
            f"|A| = {m.avaliaveis} < {DATASET_MIN} (avaliaveis insuficientes)"
        )

    if m.A > 0:
        raise GateError(f"Metrica A = {m.A} (violacoes NUNCA) > 0")

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
