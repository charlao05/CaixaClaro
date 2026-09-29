"""Workers persistentes — M6.

Escopo atual: processar sync_requests enfileirados por item/created (M3b).
Renewal e cobranca ficam para M6.3.

Padrao de claim: SELECT ... FOR UPDATE SKIP LOCKED em transacao curta,
marcando status='processando' + claimed_by/claimed_at. A chamada externa
a Pluggy roda FORA da transacao para nao segurar lock durante HTTP.

Recuperacao: linhas em 'processando' mais antigas que
PROCESSANDO_OBSOLETO_SEGUNDOS voltam para 'pendente' no inicio de cada
tick — mesma janela usada em security/idempotency.py.

Classificacao fiscal: segue o padrao de POST /transacoes/extrato/colar
(api/transacoes.py) — classifica cada transacao com processar_lancamento,
acumula delta_faturamento e chama atualizar_fiscal_state UMA VEZ ao fim
do sync. Consistente com o criterio M4 "fiscal_state atualizado no mesmo
passo da ingestao".
"""
from datetime import date
from decimal import Decimal

from ..domain.fiscal.classificacao import ContextoClassificacao
from ..security.audit import registrar_auditoria
from ..services.faturamento import atualizar_fiscal_state, conta_faturamento
from ..services.notificacoes import enviar_alertas_telegram
from . import pluggy
from .fiscal import processar_lancamento

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
                   a.provider_account_id,
                   u.regime
              FROM sync_requests sr
              JOIN accounts a ON a.id = sr.account_id
              JOIN users u ON u.id = sr.user_id
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


async def _persistir_transacoes(conn, user_id, account_id, results, regime):
    """Upsert de transacoes Pluggy + classificacao fiscal.

    Retorna (inseridas, delta_faturamento, data_mais_recente).

    Segue o padrao de POST /transacoes/extrato/colar: classifica cada
    transacao com processar_lancamento e acumula delta. O caller e que
    chama atualizar_fiscal_state uma vez no fim.
    """
    inseridas = 0
    delta = Decimal("0")
    data_mais_recente = None
    ctx = ContextoClassificacao(personal_rules={}, regime=regime)

    for tx in results:
        tx_id = tx.get("id")
        data = _normalizar_data(tx.get("date"))
        descricao = tx.get("description") or ""
        amount = tx.get("amount")
        if not tx_id or data is None or amount is None:
            continue

        valor = Decimal(str(amount))
        rf = processar_lancamento(descricao, valor, contexto=ctx)
        cat = rf.guardrail.categoria_corrigida
        c = rf.classificacao

        row = await conn.fetchval(
            """
            INSERT INTO transactions
              (user_id, account_id, origem, pluggy_tx_id,
               data, descricao_bruta, valor,
               categoria, categoria_original,
               proposito, patrimonio, tratamento_tributario,
               confianca, needs_review, via, motivo)
            VALUES ($1, $2, 'pluggy', $3, $4, $5, $6,
                    $7, $7, $8, $9, $10, $11, $12, $13, $14)
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
            cat,
            c.proposito,
            c.patrimonio,
            c.tratamento_tributario,
            c.confianca,
            rf.triagem.needs_review,
            c.via,
            c.motivo,
        )
        if row is not None:
            inseridas += 1
            if conta_faturamento(c.patrimonio, cat):
                delta += valor
                if data_mais_recente is None or data > data_mais_recente:
                    data_mais_recente = data

    return inseridas, delta, data_mais_recente


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
        cursor = None
        total_inseridas = 0
        delta_total = Decimal("0")
        data_mais_recente = None
        while True:
            payload = await pluggy.listar_transactions(
                sync["provider_account_id"], cursor=cursor
            )
            inseridas, delta, data = await _persistir_transacoes(
                conn,
                sync["user_id"],
                sync["account_id"],
                payload.get("results") or [],
                sync["regime"],
            )
            total_inseridas += inseridas
            delta_total += delta
            if data is not None:
                if data_mais_recente is None or data > data_mais_recente:
                    data_mais_recente = data
            cursor = payload.get("next")
            if not cursor:
                break

        if delta_total > 0 and data_mais_recente is not None:
            res = await atualizar_fiscal_state(
                conn, sync["user_id"], delta_total, data_mais_recente
            )
            await enviar_alertas_telegram(
                sync["user_id"], res.alertas_criados
            )

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
            meta={
                "inseridas": total_inseridas,
                "delta_faturamento": str(delta_total),
            },
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
