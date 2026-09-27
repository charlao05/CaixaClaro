"""Alertas — leitura e marcar-lido.

Alerts sao gerados pelo M4b (§10) quando o faturamento cruza
faixas 60/80/90/95/100/120%. Este modulo apenas LE e MARCA LIDO.
Nunca cria alertas — a criacao vive em services/faturamento.py.
"""
import base64
import uuid as _uuid
from datetime import datetime

from ..security.erros import erro


def _encode_cursor(ts: datetime, id_: _uuid.UUID) -> str:
    payload = f"{ts.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, _uuid.UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode()
        ts_s, id_s = raw.split("|", 1)
        return datetime.fromisoformat(ts_s), _uuid.UUID(id_s)
    except Exception as e:
        raise erro(400, "CURSOR_INVALIDO", "Cursor malformado.") from e


async def listar_alertas(
    conn,
    user_id,
    *,
    apenas_nao_lidos: bool = False,
    tipo: str | None = None,
    limite: int = 50,
    cursor: str | None = None,
):
    """Lista alertas do usuario, mais recentes primeiro. Cursor opcional."""
    cursor_ts, cursor_id = (None, None)
    if cursor:
        cursor_ts, cursor_id = _decode_cursor(cursor)

    sql = """
        SELECT id, tipo, severidade, mensagem, lido_em, criado_em,
               banda_ou_slug, prazo
          FROM alerts
         WHERE user_id = $1
           AND ($2::bool IS FALSE OR lido_em IS NULL)
           AND ($3::text IS NULL OR tipo = $3::text)
    """
    args: list = [user_id, apenas_nao_lidos, tipo]
    next_idx = 4

    if cursor_ts is not None:
        sql += (
            f" AND (criado_em < ${next_idx}::timestamptz"
            f" OR (criado_em = ${next_idx}::timestamptz"
            f" AND id < ${next_idx + 1}::uuid))"
        )
        args.extend([cursor_ts, cursor_id])
        next_idx += 2

    sql += f" ORDER BY criado_em DESC, id DESC LIMIT ${next_idx}"
    args.append(limite + 1)

    rows = await conn.fetch(sql, *args)

    has_more = len(rows) > limite
    rows = rows[:limite]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(last["criado_em"], last["id"])

    return rows, has_more, next_cursor


async def marcar_lido(conn, user_id, alerta_id):
    """Marca um alerta como lido. Idempotente.

    Retorna:
        None  -> alerta nao existe ou nao pertence ao usuario
        False -> ja estava lido (no-op)
        True  -> marcado agora
    """
    row = await conn.fetchrow(
        "SELECT lido_em FROM alerts WHERE id = $1 AND user_id = $2",
        alerta_id,
        user_id,
    )
    if row is None:
        return None
    if row["lido_em"] is not None:
        return False
    await conn.execute(
        "UPDATE alerts SET lido_em = now() WHERE id = $1",
        alerta_id,
    )
    return True
