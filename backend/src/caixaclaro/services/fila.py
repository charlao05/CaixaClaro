"""Fila de revisao + confirmacao do usuario — M5A.

Leitura: transacoes com needs_review = true, ordenadas por data DESC.
Confirmacao: usuario aceita ou corrige a categoria proposta.

Decisoes congeladas:
  - Retroatividade: A (faturamento_acumulado soma/subtrai conforme a
    categoria muda; a descida nao emite alerta novo, apenas recalcula
    banda_atual — §10 continua monotonico).
  - Auditoria: B (categoria_original preserva o que a maquina disse).
"""
import base64
import uuid as _uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ..domain.fiscal.taxonomia import get_categoria
from .faturamento import conta_faturamento


def _delta_faturamento(
    categoria_antiga: str,
    categoria_nova: str,
    patrimonio: str | None,
    valor: Decimal,
) -> Decimal:
    """Delta retroativo. Zero quando a mudanca nao toca §9."""
    antes = valor if conta_faturamento(patrimonio, categoria_antiga) else Decimal("0")
    depois = valor if conta_faturamento(patrimonio, categoria_nova) else Decimal("0")
    return Decimal(depois) - Decimal(antes)


def _encode_cursor_fila(ts, id_) -> str:
    payload = f"{ts.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor_fila(cursor: str):
    """Retorna (datetime, uuid) ou levanta ValueError."""
    padding = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + padding).decode()
    ts_s, id_s = raw.split("|", 1)
    return datetime.fromisoformat(ts_s), _uuid.UUID(id_s)


async def listar_fila(conn, user_id, *, limite: int = 50, cursor: str | None = None):
    """Transacoes em revisao, mais recentes primeiro. Cursor opcional."""
    cursor_data, cursor_id = (None, None)
    if cursor:
        try:
            cursor_data, cursor_id = _decode_cursor_fila(cursor)
        except Exception as e:
            raise ValueError("cursor malformado") from e

    sql = """
        SELECT id, data, descricao_bruta, valor, origem,
               categoria, categoria_original, proposito, patrimonio,
               tratamento_tributario, confianca, needs_review, via, motivo,
               criado_em, atualizado_em, versao
          FROM transactions
         WHERE user_id = $1 AND needs_review = true
    """
    args = [user_id]
    if cursor_data is not None:
        sql += (
            " AND (criado_em < $2::timestamptz"
            " OR (criado_em = $2::timestamptz AND id < $3::uuid))"
        )
        args.extend([cursor_data, cursor_id])
        sql += " ORDER BY criado_em DESC, id DESC LIMIT $4"
        args.append(limite + 1)
    else:
        sql += " ORDER BY criado_em DESC, id DESC LIMIT $2"
        args.append(limite + 1)

    rows = await conn.fetch(sql, *args)
    has_more = len(rows) > limite
    rows = rows[:limite]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor_fila(last["criado_em"], last["id"])

    return rows, has_more, next_cursor


async def buscar_para_confirmar(conn, user_id, tx_id):
    """Row pronta para confirmar ou None se nao encontrada / nao e do usuario."""
    return await conn.fetchrow(
        """
        SELECT id, user_id, valor, patrimonio, categoria, categoria_original,
               needs_review, confirmado_por
          FROM transactions
         WHERE id = $1 AND user_id = $2
         FOR UPDATE
        """,
        tx_id,
        user_id,
    )


@dataclass(frozen=True)
class ConfirmacaoResultado:
    tx_id: str
    categoria_antiga: str
    categoria_nova: str
    delta_faturamento: Decimal
    categoria_mudou: bool


async def confirmar(
    conn,
    user_id,
    tx_id,
    categoria_nova: str | None,
    confirmado_por: str,
):
    """Confirma uma transacao da fila. Retorna ConfirmacaoResultado.

    Erros de negocio sao levantados pelo caller (404/409). Aqui so
    a logica de dados: valida estado, atualiza linha, calcula delta.
    """
    row = await buscar_para_confirmar(conn, user_id, tx_id)
    if row is None:
        return None, "nao_encontrada"

    if row["confirmado_por"] is not None:
        return None, "ja_confirmada"

    if not row["needs_review"]:
        return None, "nao_esta_em_revisao"

    cat_antiga = row["categoria"]
    cat_nova = categoria_nova or cat_antiga

    try:
        get_categoria(cat_nova)
    except KeyError:
        return None, "categoria_invalida"

    delta = _delta_faturamento(
        cat_antiga, cat_nova, row["patrimonio"], row["valor"]
    )

    await conn.execute(
        """
        UPDATE transactions
           SET categoria = $1,
               needs_review = false,
               confirmado_por = $2,
               confirmado_em = now(),
               versao = versao + 1,
               atualizado_em = now()
         WHERE id = $3
        """,
        cat_nova,
        confirmado_por,
        tx_id,
    )

    return ConfirmacaoResultado(
        tx_id=str(tx_id),
        categoria_antiga=cat_antiga,
        categoria_nova=cat_nova,
        delta_faturamento=delta,
        categoria_mudou=(cat_antiga != cat_nova),
    ), None
