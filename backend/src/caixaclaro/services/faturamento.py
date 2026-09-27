"""Faturamento MEI — M4_CONTRATO §9 (incremento) + §10 (alertas).

Decisoes documentadas nesta implementacao:

  M4b-D1  TETO_MEI_ANUAL = 81000.00
  M4b-D2  faturamento_acumulado reinicia por ano (ano_referencia no estado)
  M4b-D3  tipo="faturamento_faixa", banda_ou_slug="enq_MEI_NN",
          prazo=31/12 do ano de competencia

Estado JSONB esperado em fiscal_state.estado:
    {
      "faturamento_acumulado": "45000.00",
      "ano_referencia": 2026,
      "banda_atual": "enq_MEI_60",
      "ultima_avaliacao_em": "2026-09-27T..."
    }
"""
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json

TETO_MEI_ANUAL = Decimal("81000.00")

# (percentual, slug, severidade)
FAIXAS: tuple[tuple[Decimal, str, str], ...] = (
    (Decimal("0.60"), "enq_MEI_60",  "informativo"),
    (Decimal("0.80"), "enq_MEI_80",  "atencao"),
    (Decimal("0.90"), "enq_MEI_90",  "atencao"),
    (Decimal("0.95"), "enq_MEI_95",  "critico"),
    (Decimal("1.00"), "enq_MEI_100", "critico"),
    (Decimal("1.20"), "enq_MEI_120", "critico"),
)

TIPO_ALERTA = "faturamento_faixa"


def _calcular_banda(faturamento: Decimal) -> str | None:
    """Retorna o slug da maior faixa atingida, ou None se abaixo de 60%.

    Independe de direcao: subir ou descer, a banda e sempre a do valor
    atual. Alertas §10 continuam monotonico-crescentes — so cruzar
    para cima emite; a descida apenas recalcula esta banda.
    """
    if faturamento <= 0:
        return None
    pct = faturamento / TETO_MEI_ANUAL
    banda: str | None = None
    for p, slug, _ in FAIXAS:
        if pct >= p:
            banda = slug
    return banda


def _load_estado(raw) -> dict:
    """asyncpg devolve JSONB como str por padrao; normaliza para dict."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def conta_faturamento(patrimonio: str | None, categoria: str | None) -> bool:
    """Regra §9: so incrementa em atividade_negocio + receita_servico|venda."""
    return (
        patrimonio == "atividade_negocio"
        and categoria in ("receita_servico", "receita_venda")
    )


def faixa_cruzada(
    antes: Decimal, depois: Decimal
) -> list[tuple[str, str, str]]:
    """Faixas cujo limiar foi cruzado no intervalo (antes, depois].

    Retorna [(slug, severidade, mensagem)] na ordem crescente das faixas.
    """
    cruzadas: list[tuple[str, str, str]] = []
    for pct, slug, sev in FAIXAS:
        limiar = TETO_MEI_ANUAL * pct
        if antes < limiar <= depois:
            msg = (
                f"Faturamento MEI cruzou {int(pct * 100)}% "
                f"do teto anual (R$ {TETO_MEI_ANUAL})."
            )
            cruzadas.append((slug, sev, msg))
    return cruzadas


def prazo_do_ano(quando: date) -> date:
    """Prazo canonico: 31/12 do ano de competencia."""
    return date(quando.year, 12, 31)


@dataclass(frozen=True)
class FaturamentoResultado:
    antes: Decimal
    depois: Decimal
    ano_referencia: int
    faixas: tuple[tuple[str, str, str], ...]
    alertas_criados: tuple[tuple[str, str, str], ...] = ()


def calcular_delta(
    estado: dict, delta: Decimal, quando: date
) -> tuple[dict, FaturamentoResultado]:
    """Retorna (novo_estado, resultado). Puro, sem I/O."""
    ano = quando.year
    estado = dict(estado)

    ano_ref = estado.get("ano_referencia")
    if ano_ref != ano:
        estado["faturamento_acumulado"] = "0"
        estado["ano_referencia"] = ano
        estado.pop("banda_atual", None)

    antes = Decimal(str(estado.get("faturamento_acumulado", "0")))
    depois = antes + delta

    estado["faturamento_acumulado"] = str(depois)
    estado["ultima_avaliacao_em"] = datetime.now(timezone.utc).isoformat()

    faixas = tuple(faixa_cruzada(antes, depois))
    # Recalcula banda_atual SEMPRE — descida tambem precisa refletir.
    # Alertas §10 seguem monotonico-crescentes (so faixa_cruzada emite).
    estado["banda_atual"] = _calcular_banda(depois)

    return estado, FaturamentoResultado(
        antes=antes,
        depois=depois,
        ano_referencia=ano,
        faixas=faixas,
    )


async def atualizar_fiscal_state(
    conn, user_id, delta: Decimal, quando: date
) -> FaturamentoResultado:
    """Aplica delta em fiscal_state + emite alertas §10. Lock FOR UPDATE.

    Retorna alertas_criados: apenas os que foram efetivamente inseridos
    (ON CONFLICT DO NOTHING suprime duplicatas sem eco).
    """
    if delta == 0:
        row = await conn.fetchrow(
            "SELECT estado FROM fiscal_state WHERE user_id = $1", user_id
        )
        estado = _load_estado(row["estado"]) if row else {}
        return FaturamentoResultado(
            antes=Decimal(str(estado.get("faturamento_acumulado", "0"))),
            depois=Decimal(str(estado.get("faturamento_acumulado", "0"))),
            ano_referencia=quando.year,
            faixas=(),
        )

    row = await conn.fetchrow(
        "SELECT estado FROM fiscal_state WHERE user_id = $1 FOR UPDATE",
        user_id,
    )
    estado_atual = _load_estado(row["estado"]) if row else {}

    novo_estado, resultado = calcular_delta(estado_atual, delta, quando)

    await conn.execute(
        """
        INSERT INTO fiscal_state (user_id, estado, atualizado_em)
        VALUES ($1, $2::jsonb, now())
        ON CONFLICT (user_id) DO UPDATE
          SET estado = EXCLUDED.estado,
              atualizado_em = now()
        """,
        user_id,
        json.dumps(novo_estado),
    )

    prazo = prazo_do_ano(quando)
    alertas_criados: list[tuple[str, str, str]] = []
    for slug, sev, msg in resultado.faixas:
        row = await conn.fetchval(
            """
            INSERT INTO alerts
              (user_id, tipo, banda_ou_slug, prazo, severidade, mensagem)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, tipo, banda_ou_slug, prazo)
              DO NOTHING
            RETURNING id
            """,
            user_id, TIPO_ALERTA, slug, prazo, sev, msg,
        )
        if row is not None:
            alertas_criados.append((slug, sev, msg))

    return replace(resultado, alertas_criados=tuple(alertas_criados))
