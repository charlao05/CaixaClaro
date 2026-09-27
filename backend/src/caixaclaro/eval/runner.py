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
DESPESAS_NEUTRAS = (
    "imposto_das", "taxas_tarifas", "custo_operacional",
    "transferencia_propria", "pessoal_prolabore", "reembolso",
    "emprestimo", "outros",
)
PALAVRAS_NUNCA_RECEITA = (
    "estorno", "devolucao", "reembolso", "ressarcimento",
    "emprestimo", "financiamento",
)
DIFFICULTIES = ("easy", "medium", "hard", "adversarial")
TAXONOMIA_ESPERADA = "v1"
DATASET_MIN = 15


def _validar_schema(casos, schema):
    """Validacao manual minima — nao depende de jsonschema externo."""
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
    def A(self) -> int: return self.violacoes
    @property
    def B(self) -> float:
        return self.acertos_avaliaveis / self.avaliaveis if self.avaliaveis else 0.0
    @property
    def C(self) -> float:
        return self.abstratidos / self.total if self.total else 0.0
    @property
    def D(self) -> int: return self.erros_criticos


def carregar_dataset(caminho: Path) -> list[dict]:
    return json.loads(caminho.read_text(encoding="utf-8"))


def carregar_schema(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def avaliar(casos: list[dict]) -> Metricas:
    if len(casos) < DATASET_MIN:
        raise ValueError(
            f"dataset tem {len(casos)} casos, minimo {DATASET_MIN}"
        )

    ctx = ContextoClassificacao(personal_rules={})
    resultados: list[CasoResultado] = []
    violacoes = acertos_avaliaveis = avaliaveis = abstratidos = erros_criticos = 0
    por_dif = defaultdict(lambda: {"total": 0, "abst": 0, "acertos": 0})

    for caso in casos:
        desc = caso["descricao"]
        valor = Decimal(str(caso["valor"]))
        esperado = caso["categoria_esperada"]
        dif = caso["difficulty"]

        classif = classificar_v2(desc, valor, ctx)
        guard = aplicar_guardrail(
            classif,
            descricao=desc,
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
            and (
                (esperado in RECEITAS and atual in DESPESAS_NEUTRAS)
                or (esperado in DESPESAS_NEUTRAS and atual in RECEITAS)
            )
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


def imprimir(m: Metricas) -> None:
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
    print("Breakdown por difficulty:")
    for dif in DIFFICULTIES:
        d = m.por_dificuldade.get(dif)
        if not d:
            continue
        print(f"  {dif:12} total={d['total']:2} abst={d['abst']:2} acertos={d['acertos']}")
    print()


def taxonomia_ok() -> bool:
    return TAXONOMIA_VERSION == TAXONOMIA_ESPERADA
