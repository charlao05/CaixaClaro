"""Handler do webhook item/created da Pluggy (M3b).

Persiste Item (consents), contas (accounts) e cria sync_requests pendentes.
Idempotente por UNIQUE parcial (migration 004).
Nao faz HTTP fora do client services.pluggy.
"""
import uuid as _uuid

from ..security.erros import erro
from . import pluggy


async def processar_item_created(conn, payload: dict) -> dict:
    """Processa um evento item/created.

    payload deve conter:
      - itemId: str
      - clientUserId: str (UUID do nosso usuario)

    Retorna {"item_id": str, "accounts": int, "sync_requests": int}.
    """
    item_id = payload.get("itemId")
    client_user_id = payload.get("clientUserId")
    if not item_id or not client_user_id:
        raise erro(
            400,
            "WEBHOOK_PAYLOAD_INVALIDO",
            "itemId e clientUserId obrigatorios.",
        )
    try:
        user_id = _uuid.UUID(str(client_user_id))
    except (ValueError, TypeError) as e:
        raise erro(
            400,
            "WEBHOOK_CLIENTUSERID_INVALIDO",
            "clientUserId nao e UUID.",
        ) from e

    # Busca antes de gravar: se a Pluggy falhar, nao criamos consent orfao.
    await pluggy.buscar_item(item_id)
    accounts = await pluggy.listar_accounts(item_id)

    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO consents (user_id, provider, provider_user_id, revogado_em)
            VALUES ($1, 'pluggy', $2, NULL)
            ON CONFLICT (provider, provider_user_id) WHERE provider = 'pluggy'
            DO UPDATE SET user_id = EXCLUDED.user_id, revogado_em = NULL
            """,
            user_id,
            item_id,
        )

        criados = 0
        for acc in accounts:
            acc_id = acc.get("id")
            if not acc_id:
                continue
            row = await conn.fetchrow(
                """
                INSERT INTO accounts (
                    user_id, provider, provider_account_id, nome, item_id
                )
                VALUES ($1, 'pluggy', $2, $3, $4)
                ON CONFLICT (provider, provider_account_id) WHERE provider = 'pluggy'
                DO UPDATE SET
                    nome = EXCLUDED.nome,
                    item_id = EXCLUDED.item_id,
                    atualizado_em = now()
                RETURNING id
                """,
                user_id,
                acc_id,
                acc.get("name"),
                item_id,
            )
            account_id_local = row["id"]

            ja_pendente = await conn.fetchval(
                """
                SELECT id FROM sync_requests
                 WHERE account_id = $1 AND status = 'pendente'
                 LIMIT 1
                """,
                account_id_local,
            )
            if ja_pendente is None:
                await conn.execute(
                    """
                    INSERT INTO sync_requests (user_id, account_id, status)
                    VALUES ($1, $2, 'pendente')
                    """,
                    user_id,
                    account_id_local,
                )
                criados += 1

    return {
        "item_id": item_id,
        "accounts": len(accounts),
        "sync_requests": criados,
    }

