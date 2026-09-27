"""Fluxo de Idempotency-Key — CONTRATOS_INTERNOS §13."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import asyncpg
from fastapi import HTTPException

from ..db import conexao
from .erros import erro

# Janela acima da qual uma chave 'processando' é considerada obsoleta.
# Cobre paste/import com folga. Operações mais longas (ex.: classificação
# em lote) podem exigir valor próprio no futuro.
PROCESSANDO_OBSOLETO_SEGUNDOS = 300


def _payload_hash(body: dict) -> str:
    canonico = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _validar_chave(chave: str) -> None:
    try:
        u = uuid.UUID(chave)
    except (ValueError, TypeError, AttributeError):
        raise erro(422, "VALIDATION_ERROR", "Idempotency-Key deve ser UUID v4.")
    if u.version != 4:
        raise erro(422, "VALIDATION_ERROR", "Idempotency-Key deve ser UUID v4.")


def _parse_jsonb(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        return json.loads(v)
    return v


async def executar_com_idempotencia(
    *,
    user_id: str,
    rota: str,
    chave: str,
    body: dict,
    operacao: Callable[[asyncpg.Connection], Awaitable[tuple[Any, int]]],
) -> tuple[Any, int]:
    _validar_chave(chave)
    uid = uuid.UUID(user_id)
    hash_payload = _payload_hash(body)
    agora = datetime.now(timezone.utc)

    async with conexao() as conn:
        inserido = await conn.fetchval(
            """
            INSERT INTO idempotency_keys
              (user_id, rota, chave, payload_hash, status,
               expira_em, atualizado_em)
            VALUES ($1, $2, $3, $4, 'processando',
                    now() + interval '24 hours', now())
            ON CONFLICT (user_id, rota, chave) DO NOTHING
            RETURNING id
            """,
            uid, rota, chave, hash_payload,
        )

        if inserido is None:
            row = await conn.fetchrow(
                """
                SELECT status, payload_hash, response, status_http, atualizado_em
                FROM idempotency_keys
                WHERE user_id = $1 AND rota = $2 AND chave = $3
                  AND expira_em > now()
                """,
                uid, rota, chave,
            )
            if row is None:
                raise erro(409, "IDEMPOTENCY_KEY_EXPIRADA",
                           "Idempotency-Key expirou. Use uma nova.")
            if row["payload_hash"] != hash_payload:
                raise erro(409, "IDEMPOTENCY_KEY_REUSED",
                           "Idempotency-Key já usada com payload diferente.")

            if row["status"] == "concluido":
                return _parse_jsonb(row["response"]), row["status_http"]

            if row["status"] == "processando":
                idade = (agora - row["atualizado_em"]).total_seconds()
                if idade < PROCESSANDO_OBSOLETO_SEGUNDOS:
                    raise erro(409, "IDEMPOTENCY_EM_ANDAMENTO",
                               "Operação em andamento.",
                               headers={"Retry-After": "1"})
                # Chave obsoleta: operação anterior morreu. Cai para reprocessar.
                await conn.execute(
                    """
                    UPDATE idempotency_keys
                    SET status='processando', response=NULL, status_http=NULL,
                        atualizado_em=now()
                    WHERE user_id=$1 AND rota=$2 AND chave=$3
                    """,
                    uid, rota, chave,
                )
            else:
                # status == 'falhou': permite retry explícito
                await conn.execute(
                    """
                    UPDATE idempotency_keys
                    SET status='processando', response=NULL, status_http=NULL,
                        atualizado_em=now()
                    WHERE user_id=$1 AND rota=$2 AND chave=$3
                    """,
                    uid, rota, chave,
                )

        try:
            async with conn.transaction():
                resposta, status_http = await operacao(conn)
                # CORREÇÃO 4.1: UPDATE de conclusão DENTRO da mesma transação
                # da operação de negócio. Se COMMIT passa, ambos persistem.
                # Se algo falha, ambos desfazem — sem janela.
                await conn.execute(
                    """
                    UPDATE idempotency_keys
                    SET status='concluido',
                        response=$4::jsonb,
                        status_http=$5,
                        atualizado_em=now()
                    WHERE user_id=$1 AND rota=$2 AND chave=$3
                    """,
                    uid, rota, chave,
                    json.dumps(resposta, ensure_ascii=False, default=str),
                    status_http,
                )
        except HTTPException as e:
            await conn.execute(
                """
                UPDATE idempotency_keys
                SET status='falhou',
                    response=$4::jsonb,
                    status_http=$5,
                    atualizado_em=now()
                WHERE user_id=$1 AND rota=$2 AND chave=$3
                """,
                uid, rota, chave,
                json.dumps(e.detail, ensure_ascii=False, default=str),
                e.status_code,
            )
            raise
        except Exception as e:
            # CORREÇÃO 4.3: exceção inesperada também marca 'falhou'.
            # Sem isso, a chave fica presa em 'processando' até o timeout
            # de 5 min — e o cliente vê 409 mesmo já sem operação ativa.
            await conn.execute(
                """
                UPDATE idempotency_keys
                SET status='falhou',
                    response=$4::jsonb,
                    status_http=500,
                    atualizado_em=now()
                WHERE user_id=$1 AND rota=$2 AND chave=$3
                """,
                uid, rota, chave,
                json.dumps({"erro": "INTERNAL_ERROR",
                            "mensagem": str(e)[:200]},
                           ensure_ascii=False),
            )
            raise

        return resposta, status_http
