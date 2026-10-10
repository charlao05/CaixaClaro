"""Apagar lançamento, desfazer uma importação e apagar repetidos.

Revisão de 2026-10-09, achado R12. Colar o extrato do mês depois de já ter
colado o da semana duplicava os lançamentos da semana (o faturamento do
painel subia junto), e não havia como apagar nada.

CONTRATOS_INTERNOS §3 proíbe usar (data, descrição, valor) como IDENTIDADE
de transação: dois lançamentos iguais no mesmo dia podem ser distintos (dois
Pix de R$ 10 do mesmo cliente). Por isso nada é descartado sozinho. O
CaixaClaro só CONTA quantos lançamentos de uma importação têm gêmeos —
mesma data, mesmo valor, mesma descrição — vindos de outra origem, avisa, e
a pessoa decide:

  - apagar os repetidos desta importação (os lançamentos de antes, que ela
    pode já ter respondido, ficam);
  - desfazer a importação inteira;
  - apagar um lançamento solto.

"Repetidos" é contado como multiconjunto: se a importação nova tem dois
lançamentos iguais e só existia um antes, só um é repetido.

Lançamento do banco conectado (Open Finance) não é apagado: ele voltaria na
próxima sincronização.
"""
import uuid as _uuid
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from ..domain.fiscal.classificacao import normalizar_descricao
from ..security.audit import registrar_auditoria
from .faturamento import (
    acumular_por_ano,
    atualizar_fiscal_state_por_ano,
    conta_faturamento,
)

ORIGENS_APAGAVEIS = ("paste", "csv", "ofx", "manual")

_COLUNAS = """
    id, origem, paste_id, import_id, line_index, data, valor, descricao_bruta,
    categoria, patrimonio, needs_review, confirmado_por
"""


def _chave(row) -> tuple[date, Decimal, str]:
    return row["data"], Decimal(row["valor"]), normalizar_descricao(row["descricao_bruta"])


async def _linhas_do_lote(conn, user_id, lote_id: str):
    return await conn.fetch(
        f"""
        SELECT {_COLUNAS}
          FROM transactions
         WHERE user_id = $1
           AND (paste_id = $2 OR import_id = $2)
         ORDER BY line_index, id
        """,
        user_id,
        lote_id,
    )


async def repetidos_do_lote(conn, user_id, lote_id: str) -> list[_uuid.UUID]:
    """Lançamentos do lote que repetem lançamentos de outra origem.

    Para cada (data, valor, descrição), repete no máximo tantos quantos
    existem fora do lote. Entre os do lote, sai primeiro o que ainda não foi
    respondido pela pessoa.
    """
    linhas = await _linhas_do_lote(conn, user_id, lote_id)
    if not linhas:
        return []

    datas = sorted({r["data"] for r in linhas})
    fora = await conn.fetch(
        """
        SELECT data, valor, descricao_bruta
          FROM transactions
         WHERE user_id = $1
           AND data = ANY($2::date[])
           AND paste_id IS DISTINCT FROM $3
           AND import_id IS DISTINCT FROM $3
        """,
        user_id,
        datas,
        lote_id,
    )
    existentes = Counter(_chave(r) for r in fora)

    por_chave: dict[tuple, list] = defaultdict(list)
    for r in linhas:
        por_chave[_chave(r)].append(r)

    escolhidos: list[_uuid.UUID] = []
    for chave, grupo in por_chave.items():
        quantos = min(len(grupo), existentes.get(chave, 0))
        if quantos == 0:
            continue
        grupo = sorted(
            grupo,
            key=lambda r: (
                r["confirmado_por"] is not None,  # não respondidos primeiro
                -(r["line_index"] or 0),
            ),
        )
        escolhidos.extend(r["id"] for r in grupo[:quantos])
    return escolhidos


async def _apagar(conn, user_id, ids: list[_uuid.UUID]) -> list:
    """Apaga as linhas e reavalia o faturamento dos anos afetados."""
    if not ids:
        return []
    apagadas = await conn.fetch(
        f"""
        DELETE FROM transactions
         WHERE user_id = $1 AND id = ANY($2::uuid[])
        RETURNING {_COLUNAS}
        """,
        user_id,
        ids,
    )
    deltas: dict[int, Decimal] = {}
    for r in apagadas:
        if conta_faturamento(r["patrimonio"], r["categoria"], r["valor"]):
            acumular_por_ano(deltas, r["data"], -Decimal(r["valor"]))
    await atualizar_fiscal_state_por_ano(conn, user_id, deltas)
    return apagadas


def _resumo_apagadas(apagadas) -> dict:
    return {
        "apagados": len(apagadas),
        "ids": [str(r["id"]) for r in apagadas],
    }


async def apagar_transacao(conn, user_id, tx_id: _uuid.UUID) -> tuple[dict | None, str | None]:
    """Apaga um lançamento. Retorna (resultado, None) ou (None, motivo)."""
    row = await conn.fetchrow(
        f"SELECT {_COLUNAS} FROM transactions WHERE id = $1 AND user_id = $2 FOR UPDATE",
        tx_id,
        user_id,
    )
    if row is None:
        return None, "nao_encontrada"
    if row["origem"] not in ORIGENS_APAGAVEIS:
        return None, "origem_bancaria"

    apagadas = await _apagar(conn, user_id, [row["id"]])
    await registrar_auditoria(
        conn,
        ator="usuario",
        acao="transacao_apagada",
        user_id=str(user_id),
        alvo=str(row["id"]),
        meta={
            "origem": row["origem"],
            "data": row["data"].isoformat(),
            "valor": str(row["valor"]),
            "categoria": row["categoria"],
            "confirmada": row["confirmado_por"] is not None,
        },
    )
    return _resumo_apagadas(apagadas), None


async def desfazer_lote(conn, user_id, lote_id: str) -> dict | None:
    """Apaga todos os lançamentos de uma colagem ou de um arquivo."""
    linhas = await _linhas_do_lote(conn, user_id, lote_id)
    if not linhas:
        return None
    apagadas = await _apagar(conn, user_id, [r["id"] for r in linhas])
    await registrar_auditoria(
        conn,
        ator="usuario",
        acao="importacao_desfeita",
        user_id=str(user_id),
        alvo=lote_id,
        meta={
            "apagados": len(apagadas),
            "confirmados_apagados": sum(r["confirmado_por"] is not None for r in apagadas),
        },
    )
    return _resumo_apagadas(apagadas)


async def apagar_repetidos(conn, user_id, lote_id: str) -> dict | None:
    """Apaga só os lançamentos do lote que repetem outros já existentes."""
    if not await _linhas_do_lote(conn, user_id, lote_id):
        return None
    apagadas = await _apagar(conn, user_id, await repetidos_do_lote(conn, user_id, lote_id))
    await registrar_auditoria(
        conn,
        ator="usuario",
        acao="repetidos_apagados",
        user_id=str(user_id),
        alvo=lote_id,
        meta={"apagados": len(apagadas)},
    )
    return _resumo_apagadas(apagadas)
