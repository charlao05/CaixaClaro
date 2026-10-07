"""Recuperacao de senha por codigo de 6 digitos — M12.

Fluxo:
  1. criar_solicitacao(conn, user_id) -> codigo raw (enviado por Telegram)
     Armazena SHA-256(codigo) em password_reset_tokens. Expiracao: 15 min.
     Criar nova solicitacao invalida a anterior (uma ativa por vez).
  2. consumir_codigo(conn, user_id, codigo) -> bool
     UPDATE ... WHERE usado_em IS NULL AND expira_em > now(),
     garantindo uso unico atomico sem SELECT+UPDATE em duas etapas.
"""
import hashlib
import secrets
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import asyncpg

EXPIRACAO_MINUTOS = 15
CODIGO_DIGITOS = 6


def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.encode("utf-8")).hexdigest()


def _gerar_codigo() -> str:
    """6 digitos, zero-padded. Espaco amostral: 000000-999999."""
    n = secrets.randbelow(10 ** CODIGO_DIGITOS)
    return str(n).zfill(CODIGO_DIGITOS)


async def criar_solicitacao(
    conn: asyncpg.Connection, user_id: str
) -> str:
    """Cria codigo de reset e devolve o valor RAW (nao persistido)."""
    raw = _gerar_codigo()
    h = _hash_codigo(raw)
    expira_em = datetime.now(timezone.utc) + timedelta(minutes=EXPIRACAO_MINUTOS)
    uid = _uuid.UUID(str(user_id))

    # uma solicitacao ativa por vez: invalida as anteriores nao usadas
    await conn.execute(
        "UPDATE password_reset_tokens SET usado_em = now() "
        "WHERE user_id = $1 AND usado_em IS NULL",
        uid,
    )
    await conn.execute(
        "INSERT INTO password_reset_tokens (user_id, codigo_hash, expira_em) "
        "VALUES ($1, $2, $3)",
        uid, h, expira_em,
    )
    return raw


async def consumir_codigo(
    conn: asyncpg.Connection, user_id: str, codigo: str
) -> bool:
    """Valida, marca usado e devolve True. False se invalido/expirado/usado."""
    if not codigo or len(codigo) != CODIGO_DIGITOS:
        return False
    h = _hash_codigo(codigo)
    row = await conn.fetchrow(
        "UPDATE password_reset_tokens SET usado_em = now() "
        "WHERE user_id = $1 AND codigo_hash = $2 "
        "  AND usado_em IS NULL AND expira_em > now() "
        "RETURNING id",
        _uuid.UUID(str(user_id)),
        h,
    )
    return row is not None