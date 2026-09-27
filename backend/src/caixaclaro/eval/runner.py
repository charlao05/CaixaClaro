"""Runner de eval — M4_CONTRATO 14."""
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from ..domain.fiscal.classificacao import ContextoClassificacao, classificar_v2
from ..domain.fiscal.guardrails import aplicar_guardrail
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


@dataclass(frozen=True)
class CasoResultado:
    id: str
    descricao: str
    esperado: str
    atual: str
    needs_review: bool
    guardrail_aplicado: bool
    guardrail_regra: str | None
    violacao: bool
    erro_critico: bool

    @property
    def acerto(self) -> bool:
        return self.atual == self.esperado


@dataclass(frozen=True)
class Metricas:
    total: int
    violacoes: int
    acertos_avaliaveis: int
    avaliaveis: int
    abstratidos: int
    erros_criticos: int
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


def avaliar(casos: list[dict]) -> Metricas:
    ctx = ContextoClassificacao(personal_rules={})
    resultados: list[CasoResultado] = []
    violacoes = acertos_avaliaveis = avaliaveis = abstratidos = erros_criticos = 0

    for caso in casos:
        desc = caso["descricao"]
        valor = Decimal(str(caso["valor"]))
        esperado = caso["categoria_esperada"]

        classif = classificar_v2(desc, valor, ctx)
        guard = aplicar_guardrail(classif, descricao=desc)
        tri = triar(classif, guard)

        atual = guard.categoria_corrigida
        norm = desc.lower()

        violacao = any(p in norm for p in PALAVRAS_NUNCA_RECEITA) and atual in RECEITAS
        erro_critico = (
            not tri.needs_review
            and (
                (esperado in RECEITAS and atual in DESPESAS_NEUTRAS)
                or (esperado in DESPESAS_NEUTRAS and atual in RECEITAS)
            )
        )

        if violacao: violacoes += 1
        if erro_critico: erros_criticos += 1

        if tri.needs_review:
            abstratidos += 1
        else:
            avaliaveis += 1
            if atual == esperado: acertos_avaliaveis += 1

        resultados.append(CasoResultado(
            id=caso["id"], descricao=desc, esperado=esperado, atual=atual,
            needs_review=tri.needs_review,
            guardrail_aplicado=guard.aplicado,
            guardrail_regra=guard.regra_acionada,
            violacao=violacao, erro_critico=erro_critico,
        ))

    return Metricas(
        total=len(casos), violacoes=violacoes,
        acertos_avaliaveis=acertos_avaliaveis, avaliaveis=avaliaveis,
        abstratidos=abstratidos, erros_criticos=erros_criticos,
        casos=resultados,
    )


def imprimir(m: Metricas) -> None:
    print()
    print(f"{'id':5} {'esperado':22} {'atual':22} {'nr':3} {'g':3} {'viola':5} {'crit':4}")
    print("-" * 72)
    for c in m.casos:
        g = (c.guardrail_regra[:3] if c.guardrail_regra else "-")
        print(f"{c.id:5} {c.esperado:22} {c.atual:22} "
              f"{'S' if c.needs_review else '.':3} {g:3} "
              f"{'V' if c.violacao else '.':5} "
              f"{'E' if c.erro_critico else '.':4}")
    print()
    print(f"total={m.total} avaliaveis={m.avaliaveis} abstratidos={m.abstratidos}")
    print(f"A violacoes      = {m.A} (esperado 0)")
    print(f"B acuracia       = {m.B:.3f} (esperado >= 0.850)")
    print(f"C abstencao      = {m.C:.3f} (esperado 0.10..0.25)")
    print(f"D erros criticos = {m.D} (esperado 0)")
    print()
