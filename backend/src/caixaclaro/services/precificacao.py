"""Orquestra o cálculo de precificação (Categoria I, docs/CONSULTA_CRC_ES.md)
e, opcionalmente, registra o cenário como hipótese do usuário — para
comparação futura com o resultado observado (REGRA_ORIENTADOR.md §3).

Registrar NÃO transforma a hipótese em fato: é apenas o armazenamento
do que o usuário informou, para consulta posterior. Nenhuma conclusão
é derivada daqui.
"""
import uuid as _uuid
from decimal import Decimal
from typing import Any

import asyncpg

from ..domain.negocio.precificacao import (
    Calculo,
    CenarioPrecificacao,
    DadosInsuficientes,
    calcular_cenario,
)
from ..security.erros import erro


def _serializar_calculo(c: Calculo) -> dict[str, Any]:
    return {
        "nome": c.nome,
        "formula": c.formula,
        "variaveis": c.variaveis,
        "resultado": c.resultado,
        "unidade": c.unidade,
        "estado": c.estado,
        "limitacao": c.limitacao,
    }


def _serializar_cenario(c: CenarioPrecificacao) -> dict[str, Any]:
    return {
        "nome": c.nome,
        "hipoteses": c.hipoteses,
        "calculos": [_serializar_calculo(x) for x in c.calculos],
        "limitacoes": c.limitacoes,
    }


async def calcular(
    conn: asyncpg.Connection,
    user_id: str,
    cenarios_in: list[dict],
    *,
    salvar: bool,
    product_id: str | None = None,
) -> dict:
    if not (1 <= len(cenarios_in) <= 2):
        raise erro(422, "VALIDATION_ERROR", "Informe de 1 a 2 cenários.")

    resultados: list[CenarioPrecificacao] = []
    for c in cenarios_in:
        try:
            cenario = calcular_cenario(
                nome=c["nome"],
                preco=c["preco"],
                custo_variavel_unitario=c["custo_variavel_unitario"],
                custos_fixos_periodo=c.get("custos_fixos_periodo"),
                volume_hipotese=c.get("volume_hipotese"),
            )
        except DadosInsuficientes as e:
            raise erro(
                422, "DADOS_INSUFICIENTES",
                f"Não é possível calcular: {e.campo} {e.motivo}.",
                extra={"campo": e.campo},
            ) from e
        resultados.append(cenario)

        if salvar:
            uid = _uuid.UUID(str(user_id))
            pid = _uuid.UUID(product_id) if product_id else None
            cfp = c.get("custos_fixos_periodo")
            vol = c.get("volume_hipotese")
            await conn.execute(
                """
                INSERT INTO pricing_scenarios
                  (user_id, product_id, nome, preco, custo_variavel_unitario,
                   custos_fixos_periodo, volume_hipotese)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                """,
                uid, pid, c["nome"],
                Decimal(str(c["preco"])),
                Decimal(str(c["custo_variavel_unitario"])),
                Decimal(str(cfp)) if cfp is not None else None,
                Decimal(str(vol)) if vol is not None else None,
            )

    return {
        "cenarios": [_serializar_cenario(r) for r in resultados],
        "comparacao": (
            "Os cenários são apresentados lado a lado, sem indicar qual é "
            "preferível — essa escolha é do usuário."
            if len(resultados) == 2 else None
        ),
    }