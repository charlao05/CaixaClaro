"""Autorizacao de uso - E1.

Decide se um usuario tem direito de uso do produto.

Funcao pura de proposito:
- nao conhece HTTP, FastAPI, nem banco;
- recebe um snapshot do estado persistido e retorna bool.

Formula (fato consolidado do billing):

    permitido =
        trial_exempt == TRUE
     OR criado_em + trial_dias > agora
     OR periodo_fim > agora

Notas de design:
- 'status' da subscription NAO entra na formula. 'pausada' com periodo
  vigente e' acesso permitido; 'pausada' com periodo vencido e' bloqueado.
  O que decide e' periodo_fim, nao o rotulo.
- 'pausada_ate' NAO entra na formula. E' agenda comercial.
- trial_exempt e' a unica excecao persistida.
- A comparacao e' estritamente maior (>), nunca >=. A fronteira exata
  (criado_em + trial_dias == agora, ou periodo_fim == agora) conta como
  expirada.
- 'agora' e' injetavel. Se None, o servico consulta o relogio real uma
  unica vez e usa o mesmo instante em todas as comparacoes.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..config import settings


@dataclass(frozen=True)
class ContextoAutorizacao:
    """Snapshot do estado persistido relevante para a autorizacao.

    Todos os datetimes devem ser timezone-aware. Espera-se UTC.
    """

    trial_exempt: bool
    criado_em: datetime
    periodo_fim: datetime | None
    agora: datetime | None = None


def decidir(ctx: ContextoAutorizacao) -> bool:
    """True se o usuario tem direito de uso. Caso contrario, False."""
    agora = ctx.agora if ctx.agora is not None else datetime.now(timezone.utc)

    if ctx.trial_exempt:
        return True

    trial_fim = ctx.criado_em + timedelta(days=settings().trial_dias)
    if trial_fim > agora:
        return True

    if ctx.periodo_fim is not None and ctx.periodo_fim > agora:
        return True

    return False