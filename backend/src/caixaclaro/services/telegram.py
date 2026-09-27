"""Telegram — vinculacao de chat por token de uso unico (M7).

Contrato: docs/CONTRATO_API.md §Telegram.
  - POST /telegram/token-vinculacao: token valido por 10 min;
    somente um ativo por usuario.
  - POST /webhooks/telegram: unico fluxo que grava telegram_chat_id.

Garantia de "um ativo" e do banco (indice parcial
telegram_link_tokens_active_uq), nao da aplicacao.
"""
import secrets
from datetime import datetime, timedelta, timezone

from ..security.audit import registrar_auditoria
from ..security.erros import erro

_TOKEN_TTL_MINUTOS = 10


def _gerar_token() -> str:
    return secrets.token_urlsafe(24)


async def gerar_token_vinculacao(conn, user_id) -> dict:
    """Fecha token ativo anterior e cria um novo. Retorna {token, expira_em}."""
    await conn.execute(
        """
        UPDATE telegram_link_tokens
           SET ativo = FALSE
         WHERE user_id = $1 AND ativo = TRUE
        """,
        user_id,
    )

    token = _gerar_token()
    expira_em = datetime.now(timezone.utc) + timedelta(
        minutes=_TOKEN_TTL_MINUTOS
    )
    await conn.execute(
        """
        INSERT INTO telegram_link_tokens (user_id, token, ativo, expira_em)
        VALUES ($1, $2, TRUE, $3)
        """,
        user_id,
        token,
        expira_em,
    )
    await registrar_auditoria(
        conn,
        ator="usuario",
        acao="TELEGRAM_TOKEN_GERADO",
        user_id=str(user_id),
        meta={"expira_em": expira_em.isoformat()},
    )
    return {"token": token, "expira_em": expira_em.isoformat()}


async def vincular_por_token(conn, token: str, chat_id: int) -> dict:
    """Resolve token ativo + nao expirado e grava users.telegram_chat_id.

    Levanta 400 TOKEN_INVALIDO se nao houver token ativo valido.
    """
    row = await conn.fetchrow(
        """
        SELECT id, user_id
          FROM telegram_link_tokens
         WHERE token = $1
           AND ativo = TRUE
           AND expira_em > now()
        """,
        token,
    )
    if row is None:
        raise erro(
            400,
            "TELEGRAM_TOKEN_INVALIDO",
            "Token invalido ou expirado.",
        )

    user_id = row["user_id"]
    await conn.execute(
        """
        UPDATE users
           SET telegram_chat_id = $1,
               atualizado_em = now()
         WHERE id = $2
        """,
        chat_id,
        user_id,
    )
    await conn.execute(
        "UPDATE telegram_link_tokens SET ativo = FALSE WHERE id = $1",
        row["id"],
    )
    await registrar_auditoria(
        conn,
        ator="webhook_telegram",
        acao="TELEGRAM_VINCULADO",
        user_id=str(user_id),
        meta={"chat_id": chat_id},
    )
    return {"user_id": str(user_id), "vinculado": True}
