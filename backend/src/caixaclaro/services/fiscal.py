"""Orquestrador fiscal M4b — CONTRATOS_INTERNOS §4 + M4_CONTRATO §5-§10.

Pipeline deterministico, sem I/O:
    classificar_v2 -> aplicar_guardrail -> triar

Nao persiste, nao decide faturamento. Só produz o ResultadoFiscal.
A persistencia e a atualizacao de fiscal_state ficam em api/transacoes.py
(que ja roda dentro de executar_com_idempotencia, transacao unica).
"""
from dataclasses import dataclass
from decimal import Decimal

from ..domain.fiscal.classificacao import (
    ClassificacaoResultado,
    ContextoClassificacao,
    classificar_v2,
)
from ..domain.fiscal.guardrails import GuardrailResultado, aplicar_guardrail
from ..domain.fiscal.triagem import TriagemResultado, triar


@dataclass(frozen=True)
class ResultadoFiscal:
    classificacao: ClassificacaoResultado
    guardrail: GuardrailResultado
    triagem: TriagemResultado


def processar_lancamento(
    descricao: str,
    valor: Decimal,
    *,
    contexto: ContextoClassificacao,
    cpf_titular_hash: str | None = None,
    cpf_contraparte_hash: str | None = None,
) -> ResultadoFiscal:
    """Aplica o pipeline completo. Nunca levanta para entrada valida."""
    classif = classificar_v2(descricao, valor, contexto)
    guard = aplicar_guardrail(
        classif,
        descricao=descricao,
        cpf_titular_hash=cpf_titular_hash,
        cpf_contraparte_hash=cpf_contraparte_hash,
    )
    tri = triar(classif, guard)
    return ResultadoFiscal(classif, guard, tri)
