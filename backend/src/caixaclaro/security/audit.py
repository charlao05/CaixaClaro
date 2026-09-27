import hashlib
import hmac
import json
import uuid as _uuid
from base64 import b64decode
from typing import Any

import asyncpg

from ..config import settings


def hash_email(email: str) -> str:
    """HMAC-SHA256 do email normalizado. Nunca reversível."""
    chave = b64decode(settings().cpf_hmac_key)
    return hmac.new(
        chave,
        email.strip().lower().encode(),
        hashlib.sha256,
    ).hexdigest()


async def registrar_auditoria(
    conn: asyncpg.Connection,
    *,
    ator: str,
    acao: str,
    user_id: str | None = None,
    alvo: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    uid = _uuid.UUID(user_id) if user_id else None

    await conn.execute(
        "INSERT INTO audit_log (user_id, ator, acao, alvo, meta) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        uid,
        ator,
        acao,
        alvo,
        json.dumps(meta or {}, ensure_ascii=False),
    )
