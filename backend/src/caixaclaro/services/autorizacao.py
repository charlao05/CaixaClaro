"""Autorizacao de uso - E1 + E2.

Decide se um usuario tem direito de uso do produto e, a partir do E2,
por que nao tem, quando nao tem.

Funcao pura de proposito:
- nao conhece HTTP, FastAPI, nem banco;
- recebe um snapshot do estado persistido e retorna uma decisao.

Formula (fato consolidado do billing):

    permitido =
        trial_exempt == TRUE
     OR criado_em + trial_dias > agora
     OR periodo_fim > agora

Motivos de bloqueio (E2):
    trial_expirado       - trial expirou e nao ha subscription registrada
    assinatura_expirada  - trial expirou e a subscription tem periodo_fim <= agora

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
- decidir() e' a interface booleana do E1. avaliar() acrescenta o motivo
  do bloqueio sem alterar a regra de autorizacao.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from ..config import settings


Motivo = Literal["trial_expirado", "assinatura_expirada"]


@dataclass(frozen=True)
class ContextoAutorizacao:
    """Snapshot do estado persistido relevante para a autorizacao.

    Todos os datetimes devem ser timezone-aware. Espera-se UTC.
    """

    trial_exempt: bool
    criado_em: datetime
    periodo_fim: datetime | None
    agora: datetime | None = None


@dataclass(frozen=True)
class Decisao:
    """Resultado de avaliar(): permitido + motivo quando bloqueado."""

    permitido: bool
    motivo: Motivo | None = None


Situacao = Literal[
    "isento", "teste", "assinatura", "trial_expirado", "assinatura_expirada"
]


def fim_do_teste(criado_em: datetime) -> datetime:
    """Instante em que o periodo de teste acaba."""
    return criado_em + timedelta(days=settings().trial_dias)


def situacao(ctx: ContextoAutorizacao) -> Situacao:
    """De onde vem o acesso (ou por que ele acabou). Unica copia da formula.

    Os tres primeiros valores sao acesso permitido; os dois ultimos sao os
    motivos de bloqueio do E2.
    """
    agora = ctx.agora if ctx.agora is not None else datetime.now(timezone.utc)

    if ctx.trial_exempt:
        return "isento"

    if fim_do_teste(ctx.criado_em) > agora:
        return "teste"

    if ctx.periodo_fim is not None and ctx.periodo_fim > agora:
        return "assinatura"

    if ctx.periodo_fim is not None:
        return "assinatura_expirada"
    return "trial_expirado"


def avaliar(ctx: ContextoAutorizacao) -> Decisao:
    """Decide acesso. Retorna Decisao com motivo quando bloqueado."""
    s = situacao(ctx)
    if s in ("trial_expirado", "assinatura_expirada"):
        return Decisao(permitido=False, motivo=s)
    return Decisao(permitido=True, motivo=None)


def decidir(ctx: ContextoAutorizacao) -> bool:
    """Interface booleana do E1. Mantida para compatibilidade."""
    return avaliar(ctx).permitido