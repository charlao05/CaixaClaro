import base64
import binascii
import uuid as _uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..api.deps import usuario
from ..db import conexao
from ..domain.ingest.parser_csv import parse_csv
from ..domain.ingest.parser_ofx import parse_ofx
from ..domain.ingest.parser_texto import ExtratoIlegivel, parse_texto
from ..domain.ingest.textnorm import calcular_paste_id
from ..security.audit import registrar_auditoria
from ..security.erros import erro
from ..security.idempotency import executar_com_idempotencia
from ..domain.fiscal.classificacao import ContextoClassificacao
from ..services.faturamento import (
    atualizar_fiscal_state,
    conta_faturamento,
)
from ..services.fiscal import processar_lancamento

router = APIRouter()


class ColarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str = Field(min_length=1)


class ImportarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formato: Literal["csv", "ofx"]
    conteudo_base64: str = Field(min_length=1)


def _serializar_resumo(r) -> dict:
    return {
        "id": str(r["id"]),
        "data": r["data"].isoformat(),
        "descricao_bruta": r["descricao_bruta"],
        "valor": str(r["valor"]),
        "origem": r["origem"],
        "line_index": r["line_index"],
    }


def _serializar_completa(r) -> dict:
    d = _serializar_resumo(r)
    d.update({
        "categoria": r["categoria"],
        "needs_review": r["needs_review"],
        "criado_em": r["criado_em"].isoformat(),
        "atualizado_em": r["atualizado_em"].isoformat(),
        "versao": r["versao"],
    })
    return d


# ============================================================
# POST /extrato/colar
# ============================================================

async def _operacao_colar(conn, user_id: str, texto: str):
    try:
        lancamentos = parse_texto(texto)
    except ExtratoIlegivel as e:
        raise erro(400, "EXTRATO_ILEGIVEL", str(e)) from e

    paste_id = calcular_paste_id(texto)
    uid = _uuid.UUID(user_id)
    importados = 0
    delta_faturamento = Decimal("0")
    data_mais_recente: date | None = None
    ctx = ContextoClassificacao(personal_rules={})

    for i, l in enumerate(lancamentos):
        rf = processar_lancamento(
            l.descricao,
            l.valor,
            contexto=ctx,
            cpf_titular_hash=None,
            cpf_contraparte_hash=None,
        )
        cat = rf.guardrail.categoria_corrigida
        c = rf.classificacao

        inserted = await conn.fetchval(
            """
            INSERT INTO transactions
              (user_id, origem, paste_id, line_index, data,
               descricao_bruta, valor,
               categoria, proposito, patrimonio, tratamento_tributario,
               confianca, needs_review, via, motivo)
            VALUES ($1, 'paste', $2, $3, $4, $5, $6,
                    $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            uid, paste_id, i, l.data, l.descricao, l.valor,
            cat, c.proposito, c.patrimonio, c.tratamento_tributario,
            c.confianca, rf.triagem.needs_review, c.via, c.motivo,
        )
        if inserted is not None:
            importados += 1
            if conta_faturamento(c.patrimonio, cat):
                delta_faturamento += Decimal(str(l.valor))
                if data_mais_recente is None or l.data > data_mais_recente:
                    data_mais_recente = l.data

    if delta_faturamento > 0 and data_mais_recente is not None:
        await atualizar_fiscal_state(
            conn, uid, delta_faturamento, data_mais_recente
        )

    rows = await conn.fetch(
        """
        SELECT id, data, descricao_bruta, valor, origem, line_index,
               categoria, needs_review, criado_em, atualizado_em, versao
        FROM transactions
        WHERE user_id = $1 AND origem = 'paste' AND paste_id = $2
        ORDER BY line_index ASC
        """,
        uid, paste_id,
    )

    await registrar_auditoria(
        conn,
        ator="usuario",
        acao="extrato_colado",
        user_id=user_id,
        meta={"paste_id": paste_id, "n": len(lancamentos),
              "importados": importados},
    )

    return {
        "paste_id": paste_id,
        "importados": importados,
        "itens": [_serializar_resumo(r) for r in rows],
    }, 201

@router.post("/extrato/colar", status_code=201)
async def colar(
    dados: ColarIn,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    u: dict = Depends(usuario),
):
    async def op(conn):
        return await _operacao_colar(conn, str(u["id"]), dados.texto)

    resposta, status_http = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota="POST /api/v1/transacoes/extrato/colar",
        chave=idempotency_key,
        body=dados.model_dump(),
        operacao=op,
    )
    return JSONResponse(content=resposta, status_code=status_http)


# ============================================================
# POST /importar
# ============================================================

async def _operacao_importar(conn, user_id: str, formato: str, bruto: bytes):
    try:
        if formato == "csv":
            lancamentos = parse_csv(bruto)
        else:
            lancamentos = parse_ofx(bruto)
    except ExtratoIlegivel as e:
        raise erro(400, "ARQUIVO_ILEGIVEL", str(e)) from e

    import_id = str(_uuid.uuid4())
    uid = _uuid.UUID(user_id)
    importados = 0

    for i, l in enumerate(lancamentos):
        inserted = await conn.fetchval(
            """
            INSERT INTO transactions
              (user_id, origem, import_id, line_index, data,
               descricao_bruta, valor)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            uid, formato, import_id, i, l.data, l.descricao, l.valor,
        )
        if inserted is not None:
            importados += 1

    rows = await conn.fetch(
        """
        SELECT id, data, descricao_bruta, valor, origem, line_index,
               categoria, needs_review, criado_em, atualizado_em, versao
        FROM transactions
        WHERE user_id = $1 AND import_id = $2
        ORDER BY line_index ASC
        """,
        uid, import_id,
    )

    await registrar_auditoria(
        conn,
        ator="usuario",
        acao="arquivo_importado",
        user_id=user_id,
        meta={"import_id": import_id, "formato": formato,
              "n": len(lancamentos), "importados": importados},
    )

    return {
        "import_id": import_id,
        "importados": importados,
        "itens": [_serializar_resumo(r) for r in rows],
    }, 201


@router.post("/importar", status_code=201)
async def importar(
    dados: ImportarIn,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    u: dict = Depends(usuario),
):
    try:
        bruto = base64.b64decode(dados.conteudo_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise erro(400, "ARQUIVO_ILEGIVEL", "Conteúdo base64 inválido.") from e
    if not bruto:
        raise erro(400, "ARQUIVO_ILEGIVEL", "Arquivo vazio.")

    async def op(conn):
        return await _operacao_importar(conn, str(u["id"]), dados.formato, bruto)

    resposta, status_http = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota="POST /api/v1/transacoes/importar",
        chave=idempotency_key,
        body=dados.model_dump(),
        operacao=op,
    )
    return JSONResponse(content=resposta, status_code=status_http)


# ============================================================
# GET /transacoes
# ============================================================

def _encode_cursor(d: date, id_: _uuid.UUID) -> str:
    payload = f"{d.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[date, _uuid.UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode()
        data_s, id_s = raw.split("|", 1)
        return date.fromisoformat(data_s), _uuid.UUID(id_s)
    except Exception as e:
        raise erro(400, "CURSOR_INVALIDO", "Cursor malformado.") from e


@router.get("")
async def listar(
    desde: date | None = Query(None),
    ate: date | None = Query(None),
    limite: int = Query(100, ge=1, le=500),
    cursor: str | None = Query(None),
    u: dict = Depends(usuario),
):
    uid = _uuid.UUID(str(u["id"]))
    cursor_data, cursor_id = (None, None)
    if cursor:
        cursor_data, cursor_id = _decode_cursor(cursor)

    sql = """
        SELECT id, data, descricao_bruta, valor, origem, line_index,
               categoria, needs_review, criado_em, atualizado_em, versao
        FROM transactions
        WHERE user_id = $1
          AND ($2::date IS NULL OR data >= $2::date)
          AND ($3::date IS NULL OR data <= $3::date)
    """
    args: list = [uid, desde, ate]
    next_idx = 4

    if cursor_data is not None:
        sql += (
            f" AND (data < ${next_idx}::date"
            f" OR (data = ${next_idx}::date AND id < ${next_idx + 1}::uuid))"
        )
        args.extend([cursor_data, cursor_id])
        next_idx += 2

    sql += f" ORDER BY data DESC, id DESC LIMIT ${next_idx}"
    args.append(limite + 1)

    async with conexao() as conn:
        rows = await conn.fetch(sql, *args)

    has_more = len(rows) > limite
    rows = rows[:limite]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(last["data"], last["id"])

    return {
        "itens": [_serializar_completa(r) for r in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
