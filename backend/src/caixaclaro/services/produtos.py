"""CRUD de produtos/serviços — módulo Meu Negócio (M11).

Dado informado ou confirmado pelo usuário — nome, custo e preço vêm
exatamente do que foi digitado. Nenhuma inferência.
"""
import uuid as _uuid
from decimal import Decimal
from typing import Any

import asyncpg

from ..security.audit import registrar_auditoria
from ..security.erros import erro


def _serializar(r: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(r["id"]),
        "tipo": r["tipo"],
        "nome": r["nome"],
        "unidade_medida": r["unidade_medida"],
        "custo_atual": str(r["custo_atual"]) if r["custo_atual"] is not None else None,
        "preco_atual": str(r["preco_atual"]) if r["preco_atual"] is not None else None,
        "controla_estoque": r["controla_estoque"],
        "ativo": r["ativo"],
        "criado_em": r["criado_em"].isoformat(),
        "atualizado_em": r["atualizado_em"].isoformat(),
    }


async def criar(
    conn: asyncpg.Connection,
    user_id: str,
    *,
    tipo: str,
    nome: str,
    unidade_medida: str,
    custo_atual: Decimal | None,
    preco_atual: Decimal | None,
    controla_estoque: bool,
) -> dict:
    uid = _uuid.UUID(str(user_id))
    row = await conn.fetchrow(
        """
        INSERT INTO products
          (user_id, tipo, nome, unidade_medida, custo_atual, preco_atual,
           controla_estoque)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        RETURNING *
        """,
        uid, tipo, nome, unidade_medida, custo_atual, preco_atual, controla_estoque,
    )
    await registrar_auditoria(
        conn, ator="usuario", acao="produto_criado", user_id=str(user_id),
        alvo=str(row["id"]), meta={"tipo": tipo, "nome": nome},
    )
    return _serializar(row)


async def listar(
    conn: asyncpg.Connection, user_id: str, *, apenas_ativos: bool = True
) -> list[dict]:
    uid = _uuid.UUID(str(user_id))
    if apenas_ativos:
        rows = await conn.fetch(
            "SELECT * FROM products WHERE user_id=$1 AND ativo ORDER BY nome", uid
        )
    else:
        rows = await conn.fetch(
            "SELECT * FROM products WHERE user_id=$1 ORDER BY nome", uid
        )
    return [_serializar(r) for r in rows]


async def obter(conn: asyncpg.Connection, user_id: str, product_id: str) -> dict:
    uid = _uuid.UUID(str(user_id))
    try:
        pid = _uuid.UUID(product_id)
    except ValueError as e:
        raise erro(404, "PRODUTO_NAO_ENCONTRADO", "Produto não encontrado.") from e
    row = await conn.fetchrow(
        "SELECT * FROM products WHERE user_id=$1 AND id=$2", uid, pid
    )
    if row is None:
        raise erro(404, "PRODUTO_NAO_ENCONTRADO", "Produto não encontrado.")
    return _serializar(row)


async def atualizar(
    conn: asyncpg.Connection, user_id: str, product_id: str, campos: dict
) -> dict:
    atual = await obter(conn, user_id, product_id)  # valida existência/posse
    if not campos:
        return atual

    uid = _uuid.UUID(str(user_id))
    pid = _uuid.UUID(product_id)

    permitidos = {
        "nome", "unidade_medida", "custo_atual", "preco_atual",
        "controla_estoque", "ativo",
    }
    sets: list[str] = []
    valores: list = []
    i = 1
    for k, v in campos.items():
        if k not in permitidos:
            continue
        sets.append(f"{k} = ${i}")
        valores.append(v)
        i += 1
    if not sets:
        return atual

    sets.append("atualizado_em = now()")
    valores += [uid, pid]
    sql = (
        f"UPDATE products SET {', '.join(sets)} "
        f"WHERE user_id=${i} AND id=${i + 1} RETURNING *"
    )
    row = await conn.fetchrow(sql, *valores)
    await registrar_auditoria(
        conn, ator="usuario", acao="produto_atualizado", user_id=str(user_id),
        alvo=product_id, meta={"campos": list(campos.keys())},
    )
    return _serializar(row)

async def remover(
    conn: asyncpg.Connection, user_id: str, product_id: str
) -> None:
    """Soft delete: marca ativo=false. Nao apaga stock_movements nem
    pricing_scenarios (FKs em cascata/set-null seriam destrutivas).

    Idempotente do ponto de vista do usuario: chamar duas vezes produz
    o mesmo estado final. Segunda chamada levanta 404 porque o produto
    deixa de ser acessivel via obter() (que filtra por user_id apenas,
    sem filtrar ativo) — aqui validamos via SELECT direto.
    """
    uid = _uuid.UUID(str(user_id))
    try:
        pid = _uuid.UUID(product_id)
    except ValueError as e:
        raise erro(404, "PRODUTO_NAO_ENCONTRADO", "Produto não encontrado.") from e

    row = await conn.fetchrow(
        "SELECT id, ativo FROM products WHERE user_id=$1 AND id=$2",
        uid, pid,
    )
    if row is None:
        raise erro(404, "PRODUTO_NAO_ENCONTRADO", "Produto não encontrado.")

    await conn.execute(
        "UPDATE products SET ativo = false, atualizado_em = now() "
        "WHERE user_id = $1 AND id = $2",
        uid, pid,
    )
    await registrar_auditoria(
        conn, ator="usuario", acao="produto_removido", user_id=str(user_id),
        alvo=product_id, meta={},
    )