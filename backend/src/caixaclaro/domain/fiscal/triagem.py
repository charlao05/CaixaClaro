"""Triagem — CONTRATOS_INTERNOS §4 + M4_CONTRATO §7.

Três disposições mutuamente exclusivas, avaliadas em ordem §7.4:
  1. fila_revisao (categoria == "outros" OU confianca < 0.7)
  2. confirmacao  (guardrail crítico OU 0.7 <= confianca < 0.9)
  3. silencioso   (todo o resto)

Runtime NÃO usa severidade — severidade é conceito de eval (§14).
"""
from dataclasses import dataclass
from typing import Literal

from .taxonomia import CategoriaId
from .classificacao import ClassificacaoResultado
from .guardrails import GuardrailResultado


Disposicao = Literal["silencioso", "confirmacao", "fila_revisao"]

_GUARDRAILS_CRITICOS = (
    "cpf_proprio",
    "emprestimo",
    "estorno",
    "ponte_pf_pj",
    "tributo",
)


@dataclass(frozen=True)
class TriagemResultado:
    disposicao: Disposicao
    needs_review: bool


def triar(
    classificacao: ClassificacaoResultado,
    guardrail: GuardrailResultado,
) -> TriagemResultado:
    """Decide a disposição. Ordem §7.4: fila_revisao -> confirmacao -> silencioso."""
    cat: CategoriaId = guardrail.categoria_corrigida
    confianca = classificacao.confianca

    # 1. fila_revisao
    if cat == "outros":
        return TriagemResultado(disposicao="fila_revisao", needs_review=True)
    if classificacao.via == "heuristica" and confianca < 0.7:
        return TriagemResultado(disposicao="fila_revisao", needs_review=True)

    # 2. confirmacao
    if guardrail.aplicado and guardrail.regra_acionada in _GUARDRAILS_CRITICOS:
        return TriagemResultado(disposicao="confirmacao", needs_review=True)
    if (
        classificacao.via == "heuristica"
        and 0.7 <= confianca < 0.9
    ):
        return TriagemResultado(disposicao="confirmacao", needs_review=True)

    # 3. silencioso
    return TriagemResultado(disposicao="silencioso", needs_review=False)
