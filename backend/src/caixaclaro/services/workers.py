"""Workers persistentes — M6.

Escopo atual: processar sync_requests enfileirados por item/created (M3b).
Renewal e cobranca ficam para M6.3.

Padrao de claim: SELECT ... FOR UPDATE SKIP LOCKED em transacao curta,
marcando status='processando' + claimed_by/claimed_at. A chamada externa
a Pluggy roda FORA da transacao para nao segurar lock durante HTTP.

Recuperacao: linhas em 'processando' mais antigas que
PROCESSANDO_OBSOLETO_SEGUNDOS voltam para 'pendente' no inicio de cada
tick — mesma janela usada em security/idempotency.py.
"""
from datetime import date
from decimal import Decimal

from ..security.audit import registrar_auditoria
from . import pluggy

PROCESSANDO_OBSOLETO_SEGUNDOS = 300


async def recuperar_processando_antigos(
    conn, segundos: int = PROCESSANDO_OBSOLETO_SEGUNDOS
) -> int:
    """Devolve syncs travados em 'processando' para 'pendente'.

    Retorna o numero de linhas afetadas. Roda no inicio de cada tick.
    """
    status = await conn.execute(
        """
        UPDATE sync_requests
           SET status = 'pendente',
               claimed_at = NULL,
               claimed_by = NULL,
               erro = COALESCE(erro, 'timeout em processando'),
               atualizado_em = now()
         WHERE status = 'processando'
           AND claimed_at < now() - ($1::int * interval '1 second')
        """,
        segundos,
    )
    return int(status.split()[-1]) if status.startswith("UPDATE") else 0


async def _reivindicar_sync(conn, worker_id: str):
    """Claim de um sync pendente. Retorna row ou None.

    FOR UPDATE OF sr SKIP LOCKED garante que dois workers concorrentes
    nunca pegam o mesmo registro. A transacao aqui e curta — o status
    persistido substitui o lock quando ela termina.
    """
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT sr.id, sr.user_id, sr.account_id,
                   a.provider_account_id
              FROM sync_requests sr
              JOIN accounts a ON a.id = sr.account_id
             WHERE sr.status = 'pendente'
             ORDER BY sr.criado_em
             LIMIT 1
             FOR UPDATE OF sr SKIP LOCKED
            """
        )
        if row is None:
            return None
        await conn.execute(
            """
            UPDATE sync_requests
               SET status = 'processando',
                   claimed_at = now(),
                   claimed_by = $1,
                   tentativa_em = now(),
                   atualizado_em = now()
             WHERE id = $2
            """,
            worker_id,
            row["id"],
        )
    return row


def _normalizar_data(valor):
    """Converte 'YYYY-MM-DD' para date. asyncpg exige objeto date em DATE."""
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        return date.fromisoformat(valor[:10])
    return None


async def _persistir_transacoes(conn, user_id, account_id, results) -> int:
    """Upsert de transacoes Pluggy por (user_id, pluggy_tx_id).

    Nao classifica — classificacao e M4, disparada em fluxo separado.
    Retorna o numero de linhas efetivamente inseridas (nao conflitos).
    """
    inseridas = 0
    for tx in results:
        tx_id = tx.get("id")
        data = _normalizar_data(tx.get("date"))
        descricao = tx.get("description") or ""
        amount = tx.get("amount")
        if not tx_id or data is None or amount is None:
            continue
        valor = Decimal(str(amount))
        row = await conn.fetchval(
            """
            INSERT INTO transactions
              (user_id, account_id, origem, pluggy_tx_id,
               data, descricao_bruta, valor)
            VALUES ($1, $2, 'pluggy', $3, $4, $5, $6)
            ON CONFLICT (user_id, pluggy_tx_id)
                WHERE pluggy_tx_id IS NOT NULL
            DO NOTHING
            RETURNING id
            """,
            user_id,
            account_id,
            tx_id,
            data,
            descricao,
            valor,
        )
        if row is not None:
            inseridas += 1
    return inseridas


async def processar_um_sync(conn, worker_id: str) -> bool:
    """Processa no maximo um sync_request. Retorna True se algo foi feito.

    Recupera travados antigos antes de tentar. Nao levanta excecao para
    falha de negocio — marca o sync como 'failed' e segue.
    """
    await recuperar_processando_antigos(conn)

    sync = await _reivindicar_sync(conn, worker_id)
    if sync is None:
        return False

    try:
        page = 1
        total_inseridas = 0
        while True:
            payload = await pluggy.listar_transactions(
                sync["provider_account_id"], page=page
            )
            total_inseridas += await _persistir_transacoes(
                conn,
                sync["user_id"],
                sync["account_id"],
                payload.get("results") or [],
            )
            total_pages = payload.get("totalPages") or 1
            if page >= total_pages:
                break
            page += 1

        await conn.execute(
            """
            UPDATE sync_requests
               SET status = 'completed',
                   erro = NULL,
                   atualizado_em = now()
             WHERE id = $1
            """,
            sync["id"],
        )
        await registrar_auditoria(
            conn,
            ator="worker",
            acao="SYNC_COMPLETED",
            user_id=str(sync["user_id"]),
            alvo=str(sync["id"]),
            meta={"inseridas": total_inseridas},
        )
    except Exception as e:
        await conn.execute(
            """
            UPDATE sync_requests
               SET status = 'failed',
                   erro = $1,
                   atualizado_em = now()
             WHERE id = $2
            """,
            str(e)[:500],
            sync["id"],
        )
        await registrar_auditoria(
            conn,
            ator="worker",
            acao="SYNC_FAILED",
            user_id=str(sync["user_id"]),
            alvo=str(sync["id"]),
            meta={"erro": str(e)[:200]},
        )
    return True
