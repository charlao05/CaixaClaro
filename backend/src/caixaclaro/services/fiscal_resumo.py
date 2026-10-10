"""Resumo fiscal — soma dos lancamentos do ano + alerts.

Deriva de M4_CONTRATO §9 (estado) e §10 (faixas).

Retorna um payload pronto para o frontend. Nao escreve nada — so leitura.

O numero do painel e somado na hora, direto de `transactions` (a soma do
ano de referencia). `fiscal_state` guarda so o retrato da ultima avaliacao;
daqui se le dele apenas `ultima_avaliacao_em`.

2026-10-09: o resumo passou a respeitar o perfil do usuario. O limite anual
so existe para MEI (e e proporcional no ano de abertura); para Simples e
pessoa fisica `teto_anual`, `percentual_consumido` e `proxima_faixa` sao
null e `faixas` vem vazia, em vez de exibir o teto do MEI por omissao
(REGRA_ORIENTADOR §2.4). Tambem traz contagens e a soma de entradas e
saidas do mes mais recente com lancamentos — soma simples sobre o que o
usuario trouxe, sem classificacao.
"""
import json
from dataclasses import dataclass
from decimal import Decimal

from .faturamento import (
    FAIXAS,
    TETO_MEI_ANUAL,
    calcular_banda,
    ano_de_referencia,
    somar_faturamento_do_ano,
    teto_do_ano,
)


def _load_estado(raw) -> dict:
    """asyncpg devolve JSONB como str por padrao; normaliza para dict."""
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


def _faixas_atingidas(
    faturamento: Decimal, teto: Decimal | None = TETO_MEI_ANUAL
) -> list[FaixaResumo]:
    resultado: list[FaixaResumo] = []
    if teto is None:
        return resultado
    for pct, slug, sev in FAIXAS:
        limiar = teto * pct
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
    ultima = estado.get("ultima_avaliacao_em")

    ano_ref = await ano_de_referencia(conn, user_id)
    faturamento = await somar_faturamento_do_ano(conn, user_id, ano_ref)

    perfil = await conn.fetchrow(
        "SELECT regime, mes_abertura_mei, ano_abertura_mei "
        "FROM users WHERE id = $1",
        user_id,
    )
    regime = perfil["regime"] if perfil else "MEI"
    teto = (
        teto_do_ano(
            regime,
            perfil["mes_abertura_mei"],
            perfil["ano_abertura_mei"],
            ano_ref,
        )
        if perfil
        else TETO_MEI_ANUAL
    )

    percentual = (
        round(float(faturamento / teto), 4) if teto is not None and teto > 0 else None
    )
    faixas = _faixas_atingidas(faturamento, teto)
    proxima = _proxima_faixa(faturamento, faixas)
    banda = calcular_banda(faturamento, teto)

    alertas_nao_lidos = await conn.fetchval(
        "SELECT COUNT(*) FROM alerts WHERE user_id = $1 AND lido_em IS NULL",
        user_id,
    )

    contagem = await conn.fetchrow(
        "SELECT COUNT(*) AS total, "
        "       COUNT(*) FILTER (WHERE needs_review IS TRUE) AS pendentes, "
        "       MAX(data) AS ultima_data "
        "  FROM transactions WHERE user_id = $1",
        user_id,
    )
    total = int(contagem["total"])
    pendentes = int(contagem["pendentes"])

    mes_referencia = None
    entradas_mes = None
    saidas_mes = None
    if contagem["ultima_data"] is not None:
        ultima_data = contagem["ultima_data"]
        inicio = ultima_data.replace(day=1)
        somas = await conn.fetchrow(
            "SELECT COALESCE(SUM(valor) FILTER (WHERE valor > 0), 0) AS entradas, "
            "       COALESCE(SUM(valor) FILTER (WHERE valor < 0), 0) AS saidas "
            "  FROM transactions "
            " WHERE user_id = $1 AND data >= $2 AND data <= $3",
            user_id, inicio, ultima_data,
        )
        mes_referencia = inicio.strftime("%Y-%m")
        entradas_mes = str(somas["entradas"])
        saidas_mes = str(abs(somas["saidas"]))

    return {
        "ano_referencia": ano_ref,
        "regime": regime,
        "faturamento_acumulado": str(faturamento),
        "teto_anual": str(teto) if teto is not None else None,
        "limite_proporcional": teto is not None and teto != TETO_MEI_ANUAL,
        "percentual_consumido": percentual,
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
        "tem_transacoes": total > 0,
        "total_lancamentos": total,
        "pendentes_revisao": pendentes,
        "mes_referencia": mes_referencia,
        "entradas_mes": entradas_mes,
        "saidas_mes": saidas_mes,
    }
