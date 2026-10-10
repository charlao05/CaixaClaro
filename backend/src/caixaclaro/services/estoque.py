"""Registro de movimentações de estoque — módulo Meu Negócio (M11).

Categoria II da consulta ao CRC-ES: consolidação de eventos que o
próprio usuário registra. Não infere produto nem quantidade a partir
de uma transação bancária — `referencia_transacao_id` é um vínculo
opcional e informativo, nunca o gatilho automático do movimento.

Concorrência: o saldo é sempre derivado por soma (SUM) do histórico
de movimentos, nunca armazenado de forma redundante — mesmo princípio
de "PostgreSQL como fonte de verdade" do resto do projeto. A linha de
`products` é travada (FOR UPDATE) antes do cálculo para serializar
dois registros simultâneos do mesmo produto.
"""
import uuid as _uuid
from decimal import Decimal
from typing import Any

import asyncpg

from ..domain.negocio.estoque import EstoqueNegativoRecusado, aplicar_movimento
from ..domain.negocio.taxonomia_movimento import tipo_movimento_valido
from ..security.audit import registrar_auditoria
from ..security.erros import erro

# Mesmos valores do CHECK de stock_movements.origem (migration 011).
ORIGENS_VALIDAS = ("manual", "importado")


def _serializar(r: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(r["id"]),
        "product_id": str(r["product_id"]),
        "tipo_movimento": r["tipo_movimento"],
        "quantidade": str(r["quantidade"]),
        "origem": r["origem"],
        "referencia_transacao_id": (
            str(r["referencia_transacao_id"])
            if r["referencia_transacao_id"] else None
        ),
        "nota": r["nota"],
        "criado_em": r["criado_em"].isoformat(),
    }


async def saldo_atual(
    conn: asyncpg.Connection, user_id: str, product_id: str
) -> Decimal:
    uid = _uuid.UUID(str(user_id))
    pid = _uuid.UUID(product_id)
    row = await conn.fetchrow(
        """
        SELECT COALESCE(SUM(
          CASE WHEN tipo_movimento LIKE 'entrada_%' THEN quantidade
               ELSE -quantidade END
        ), 0) AS saldo
        FROM stock_movements
        WHERE user_id=$1 AND product_id=$2
        """,
        uid, pid,
    )
    return row["saldo"]


async def registrar_movimento(
    conn: asyncpg.Connection,
    user_id: str,
    product_id: str,
    *,
    tipo_movimento: str,
    quantidade: Decimal,
    origem: str = "manual",
    referencia_transacao_id: str | None = None,
    nota: str | None = None,
) -> dict:
    if not tipo_movimento_valido(tipo_movimento):
        raise erro(
            422, "TIPO_MOVIMENTO_INVALIDO",
            f"Tipo de movimento desconhecido: {tipo_movimento}.",
        )
    if quantidade <= 0:
        raise erro(422, "VALIDATION_ERROR", "Quantidade deve ser maior que zero.")
    # Entradas malformadas devolviam 500 (revisão de 2026-10-09, item 35 do
    # relatório de estado): id de produto inválido, origem fora da lista do
    # banco e referência que não é UUID ou não existe.
    if origem not in ORIGENS_VALIDAS:
        raise erro(422, "VALIDATION_ERROR", f"Origem desconhecida: {origem}.")

    uid = _uuid.UUID(str(user_id))
    try:
        pid = _uuid.UUID(product_id)
    except ValueError as e:
        raise erro(404, "PRODUTO_NAO_ENCONTRADO", "Produto não encontrado.") from e

    ref_uuid = None
    if referencia_transacao_id:
        try:
            ref_uuid = _uuid.UUID(referencia_transacao_id)
        except ValueError as e:
            raise erro(
                422, "VALIDATION_ERROR", "Lançamento de referência inválido."
            ) from e
        # Só um lançamento do próprio usuário pode ser referência.
        existe = await conn.fetchval(
            "SELECT 1 FROM transactions WHERE id = $1 AND user_id = $2",
            ref_uuid, uid,
        )
        if existe is None:
            raise erro(
                422, "VALIDATION_ERROR", "Lançamento de referência não encontrado."
            )

    produto = await conn.fetchrow(
        "SELECT id FROM products WHERE user_id=$1 AND id=$2 FOR UPDATE", uid, pid,
    )
    if produto is None:
        raise erro(404, "PRODUTO_NAO_ENCONTRADO", "Produto não encontrado.")

    saldo = await saldo_atual(conn, user_id, product_id)
    try:
        aplicar_movimento(saldo, tipo_movimento, quantidade)
    except EstoqueNegativoRecusado as e:
        raise erro(
            409, "ESTOQUE_NEGATIVO_RECUSADO", str(e),
            extra={
                "saldo_atual": str(e.saldo_atual),
                "quantidade": str(e.quantidade),
            },
        ) from e

    row = await conn.fetchrow(
        """
        INSERT INTO stock_movements
          (user_id, product_id, tipo_movimento, quantidade, origem,
           referencia_transacao_id, nota)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        RETURNING *
        """,
        uid, pid, tipo_movimento, quantidade, origem, ref_uuid, nota,
    )
    await registrar_auditoria(
        conn, ator="usuario", acao="estoque_movimento_registrado", user_id=str(user_id),
        alvo=str(row["id"]),
        meta={
            "product_id": product_id,
            "tipo_movimento": tipo_movimento,
            "quantidade": str(quantidade),
        },
    )
    return _serializar(row)


async def listar_movimentos(
    conn: asyncpg.Connection, user_id: str, product_id: str
) -> list[dict]:
    uid = _uuid.UUID(str(user_id))
    pid = _uuid.UUID(product_id)
    rows = await conn.fetch(
        "SELECT * FROM stock_movements WHERE user_id=$1 AND product_id=$2 "
        "ORDER BY criado_em DESC",
        uid, pid,
    )
    return [_serializar(r) for r in rows]