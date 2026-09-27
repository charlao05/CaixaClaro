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

async def revogar_item(conn, user_id, account_id) -> dict:
    """Revoga o Item Pluggy ao qual a conta pertence.

    Ordem obrigatoria: consulta Pluggy ANTES de marcar revogado_em.
    Se o DELETE externo falhar, nada e marcado localmente.
    Idempotente: consent ja revogado -> nao chama Pluggy de novo.
    """
    row = await conn.fetchrow(
        "SELECT item_id FROM accounts WHERE id = $1 AND user_id = $2",
        account_id,
        user_id,
    )
    if row is None:
        raise erro(404, "CONTA_NAO_ENCONTRADA", "Conta nao encontrada.")
    item_id = row["item_id"]
    if not item_id:
        raise erro(409, "CONTA_SEM_ITEM", "Conta sem Item Pluggy vinculado.")

    consent = await conn.fetchrow(
        """
        SELECT revogado_em FROM consents
         WHERE provider = 'pluggy'
           AND provider_user_id = $1
           AND user_id = $2
        """,
        item_id,
        user_id,
    )
    if consent and consent["revogado_em"] is not None:
        return {"item_id": item_id, "ja_revogado": True}

    await pluggy.revogar_item(item_id)

    await conn.execute(
        """
        UPDATE consents
           SET revogado_em = now()
         WHERE provider = 'pluggy'
           AND provider_user_id = $1
           AND user_id = $2
           AND revogado_em IS NULL
        """,
        item_id,
        user_id,
    )
    return {"item_id": item_id, "ja_revogado": False}

async def iniciar_sync(conn, user_id, account_id) -> dict:
    """Retorna sync_request pendente ou cria um novo.

    Idempotente: se ja existe pendente para a conta, reusa.
    Nao executa sync — apenas enfileira (worker e M6).
    """
    row = await conn.fetchrow(
        "SELECT id FROM accounts WHERE id = $1 AND user_id = $2",
        account_id,
        user_id,
    )
    if row is None:
        raise erro(404, "CONTA_NAO_ENCONTRADA", "Conta nao encontrada.")

    existente = await conn.fetchrow(
        """
        SELECT id, status FROM sync_requests
         WHERE account_id = $1 AND status = 'pendente'
         LIMIT 1
        """,
        account_id,
    )
    if existente is not None:
        return {"sync_id": str(existente["id"]), "status": existente["status"]}

    novo = await conn.fetchrow(
        """
        INSERT INTO sync_requests (user_id, account_id, status)
        VALUES ($1, $2, 'pendente')
        RETURNING id, status
        """,
        user_id,
        account_id,
    )
    return {"sync_id": str(novo["id"]), "status": novo["status"]}


async def obter_sync(conn, user_id, sync_id) -> dict:
    """Retorna estado de um sync_request do usuario. 404 se nao existir."""
    row = await conn.fetchrow(
        """
        SELECT id, status, erro, criado_em
          FROM sync_requests
         WHERE id = $1 AND user_id = $2
        """,
        sync_id,
        user_id,
    )
    if row is None:
        raise erro(404, "SYNC_NAO_ENCONTRADO", "Sincronizacao nao encontrada.")
    return {
        "sync_id": str(row["id"]),
        "status": row["status"],
        "erro": row["erro"],
        "criado_em": row["criado_em"].isoformat(),
    }



