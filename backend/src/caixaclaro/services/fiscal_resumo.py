"""Resumo fiscal — leitura de fiscal_state + alerts.

Deriva de M4_CONTRATO §9 (estado) e §10 (faixas).

Retorna um payload pronto para o frontend: quanto ja foi faturado,
quanto falta para a proxima faixa, quais alertas estao pendentes.
Nao escreve nada — so leitura.
"""
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .faturamento import FAIXAS, TETO_MEI_ANUAL


def _load_estado(raw) -> dict:
    """Mesma normalizacao de services/faturamento._load_estado."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


@dataclass(frozen=True)
class FaixaResumo:
    slug: str
    percentual: float
    severidade: str
    limiar: Decimal
    atingida: bool


def _faixas_atingidas(faturamento: Decimal) -> list[FaixaResumo]:
    resultado: list[FaixaResumo] = []
    for pct, slug, sev in FAIXAS:
        limiar = TETO_MEI_ANUAL * pct
        resultado.append(FaixaResumo(
            slug=slug,
            percentual=float(pct),
            severidade=sev,
            limiar=limiar,
            atingida=faturamento >= limiar,
        ))
    return resultado


def _proxima_faixa(
    faturamento: Decimal,
    faixas: list[FaixaResumo],
) -> dict | None:
    for f in faixas:
        if not f.atingida:
            falta = f.limiar - faturamento
            return {
                "slug": f.slug,
                "percentual": f.percentual,
                "limiar": str(f.limiar),
                "falta": str(falta),
            }
    return None


async def resumo(conn, user_id) -> dict:
    """Leitura pura do estado fiscal do usuario."""
    row = await conn.fetchrow(
        "SELECT estado FROM fiscal_state WHERE user_id = $1",
        user_id,
    )
    estado = _load_estado(row["estado"]) if row else {}

    fat_str = estado.get("faturamento_acumulado", "0")
    faturamento = Decimal(str(fat_str))
    ano_ref = estado.get("ano_referencia", date.today().year)
    banda = estado.get("banda_atual")
    ultima = estado.get("ultima_avaliacao_em")

    percentual = (
        float(faturamento / TETO_MEI_ANUAL) if TETO_MEI_ANUAL > 0 else 0.0
    )

    faixas = _faixas_atingidas(faturamento)
    proxima = _proxima_faixa(faturamento, faixas)

    alertas_nao_lidos = await conn.fetchval(
        "SELECT COUNT(*) FROM alerts WHERE user_id = $1 AND lido_em IS NULL",
        user_id,
    )

    return {
        "ano_referencia": ano_ref,
        "faturamento_acumulado": str(faturamento),
        "teto_anual": str(TETO_MEI_ANUAL),
        "percentual_consumido": round(percentual, 4),
        "banda_atual": banda,
        "ultima_avaliacao_em": ultima,
        "faixas": [
            {
                "slug": f.slug,
                "percentual": f.percentual,
                "severidade": f.severidade,
                "limiar": str(f.limiar),
                "atingida": f.atingida,
            }
            for f in faixas
        ],
        "proxima_faixa": proxima,
        "alertas_nao_lidos": alertas_nao_lidos,
    }
