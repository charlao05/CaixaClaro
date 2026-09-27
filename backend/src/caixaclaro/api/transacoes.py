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
from ..domain.fiscal.classificacao import (
    ContextoClassificacao,
    classificar_v2,
)
from ..domain.fiscal.guardrails import aplicar_guardrail
from ..domain.fiscal.triagem import triar
from ..services.faturamento import (
    atualizar_fiscal_state,
    conta_faturamento,
)
from ..services.fiscal import processar_lancamento
from ..services.tax_opinion import generate_tax_opinion
from ..services.fiscal_resumo import resumo as resumo_fiscal
from ..services.fila import confirmar as confirmar_tx, listar_fila
from ..services.alertas import listar_alertas, marcar_lido

from ..domain.fiscal.classificacao import ClassificacaoResultado
from ..domain.fiscal.guardrails import GuardrailResultado
from ..domain.fiscal.triagem import TriagemResultado
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
               categoria, categoria_original,
               proposito, patrimonio, tratamento_tributario,
               confianca, needs_review, via, motivo)
            VALUES ($1, 'paste', $2, $3, $4, $5, $6,
                    $7, $7, $8, $9, $10, $11, $12, $13, $14)
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

# ============================================================
# GET /transacoes/fila — M5A
# ============================================================

def _serializar_fila(r) -> dict:
    return {
        "id": str(r["id"]),
        "data": r["data"].isoformat(),
        "descricao_bruta": r["descricao_bruta"],
        "valor": str(r["valor"]),
        "origem": r["origem"],
        "categoria": r["categoria"],
        "categoria_original": r["categoria_original"],
        "proposito": r["proposito"],
        "patrimonio": r["patrimonio"],
        "tratamento_tributario": r["tratamento_tributario"],
        "confianca": float(r["confianca"]) if r["confianca"] is not None else None,
        "needs_review": r["needs_review"],
        "via": r["via"],
        "motivo": r["motivo"],
        "criado_em": r["criado_em"].isoformat(),
        "atualizado_em": r["atualizado_em"].isoformat(),
        "versao": r["versao"],
    }


@router.get("/fila")
async def fila(
    request: Request,
    limite: int = Query(50, ge=1, le=500),
    cursor: str | None = Query(None),
    u: dict = Depends(usuario),
):
    try:
        async with conexao() as conn:
            rows, has_more, next_cursor = await listar_fila(
                conn, _uuid.UUID(str(u["id"])),
                limite=limite, cursor=cursor,
            )
    except ValueError as e:
        raise erro(400, "CURSOR_INVALIDO", "Cursor malformado.") from e

    return {
        "itens": [_serializar_fila(r) for r in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ============================================================
# PATCH /transacoes/{id}/confirmar — M5A
# ============================================================

class ConfirmarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categoria: str | None = None


@router.patch("/{tx_id}/confirmar")
async def confirmar_endpoint(
    tx_id: str,
    dados: ConfirmarIn,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    u: dict = Depends(usuario),
):
    async def op(conn):
        return await _operacao_confirmar(
            conn, str(u["id"]), tx_id, dados.categoria
        )

    resposta, status_http = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota=f"PATCH /api/v1/transacoes/{tx_id}/confirmar",
        chave=idempotency_key,
        body={"tx_id": tx_id, **dados.model_dump()},
        operacao=op,
    )
    return JSONResponse(content=resposta, status_code=status_http)


async def _operacao_confirmar(conn, user_id, tx_id, categoria_nova):
    try:
        tx_uuid = _uuid.UUID(tx_id)
    except ValueError:
        raise erro(400, "ID_INVALIDO", "ID da transacao invalido")

    resultado, motivo = await confirmar_tx(
        conn, _uuid.UUID(user_id), tx_uuid, categoria_nova, user_id
    )

    if resultado is None:
        if motivo == "nao_encontrada":
            raise erro(404, "TX_NAO_ENCONTRADA", "Transacao nao encontrada")
        if motivo == "ja_confirmada":
            raise erro(409, "JA_CONFIRMADA", "Transacao ja foi confirmada")
        if motivo == "nao_esta_em_revisao":
            raise erro(
                409, "NAO_EM_REVISAO",
                "Transacao nao esta em fila de revisao",
            )
        if motivo == "categoria_invalida":
            raise erro(
                400, "CATEGORIA_INVALIDA",
                f"Categoria desconhecida: {categoria_nova}",
            )
        raise erro(500, "ERRO_INTERNO", "Motivo desconhecido")

    # Retroatividade: se a categoria mudou e afeta §9, atualiza fiscal_state.
    if resultado.delta_faturamento != 0:
        data_tx = await conn.fetchval(
            "SELECT data FROM transactions WHERE id = $1", tx_uuid
        )
        await atualizar_fiscal_state(
            conn, _uuid.UUID(user_id), resultado.delta_faturamento, data_tx
        )

    # Auditoria
    await registrar_auditoria(
        conn,
        ator="usuario",
        acao="transacao_confirmada",
        user_id=user_id,
        meta={
            "tx_id": tx_id,
            "categoria_antiga": resultado.categoria_antiga,
            "categoria_nova": resultado.categoria_nova,
            "delta_faturamento": str(resultado.delta_faturamento),
        },
    )

    return {
        "tx_id": resultado.tx_id,
        "categoria_antiga": resultado.categoria_antiga,
        "categoria_nova": resultado.categoria_nova,
        "delta_faturamento": str(resultado.delta_faturamento),
        "categoria_mudou": resultado.categoria_mudou,
    }, 200

# ============================================================
# GET /transacoes/{tx_id}/opiniao — CONTRATOS_INTERNOS §6
# ============================================================

def _serializar_opcao(o) -> dict:
    return {
        "label": o.label,
        "proposito": o.proposito,
        "descricao": o.descricao,
    }


@router.get("/{tx_id}/opiniao")
async def opiniao_endpoint(
    tx_id: str,
    u: dict = Depends(usuario),
):
    async with conexao() as conn:
        return await _operacao_opiniao(conn, str(u["id"]), tx_id)


async def _operacao_opiniao(conn, user_id, tx_id):
    try:
        tx_uuid = _uuid.UUID(tx_id)
    except ValueError:
        raise erro(400, "ID_INVALIDO", "ID da transacao invalido")

    row = await conn.fetchrow(
        """
        SELECT descricao_bruta, valor, categoria, categoria_original,
               proposito, patrimonio, tratamento_tributario,
               confianca, needs_review, via, confirmado_por
          FROM transactions
         WHERE id = $1 AND user_id = $2
        """,
        tx_uuid,
        _uuid.UUID(user_id),
    )
    if row is None:
        raise erro(404, "TX_NAO_ENCONTRADA", "Transacao nao encontrada")

    # §6: generate_tax_opinion(tx, classif, context) recebe classif
    # como ENTRADA. Lemos o estado PERSISTIDO — nao recomputamos o
    # pipeline. Recomputar mente quando o usuario confirma categoria
    # diferente da proposta (M5A).
    cat_atual = row["categoria"] or "outros"
    classif = ClassificacaoResultado(
        categoria=cat_atual,
        proposito=row["proposito"] or "outros_indeterminado",
        origem_sugerida="desconhecido",
        patrimonio=row["patrimonio"] or "pessoa_fisica",
        tratamento_tributario=row["tratamento_tributario"]
                              or "indeterminado_pendente",
        confianca=float(row["confianca"]) if row["confianca"] is not None else 0.0,
        needs_review=bool(row["needs_review"]),
        via=row["via"] or "heuristica",
        motivo=None,
    )

    cat_orig = row["categoria_original"] or cat_atual
    guard = GuardrailResultado(
        aplicado=(cat_orig != cat_atual),
        categoria_original=cat_orig,
        categoria_corrigida=cat_atual,
        motivo="",
        regra_acionada=None,
    )

    tri = TriagemResultado(
        disposicao="silencioso",
        needs_review=bool(row["needs_review"]),
    )

    opiniao = generate_tax_opinion(
        descricao=row["descricao_bruta"],
        valor=row["valor"],
        classif=classif,
        guard=guard,
        tri=tri,
    )

    return {
        "tx_id": tx_id,
        "fato": opiniao.fato,
        "interpretacao": opiniao.interpretacao,
        "relacao_pf_pj": opiniao.relacao_pf_pj,
        "possivel_tratamento_tributario": opiniao.possivel_tratamento_tributario,
        "condicoes_necessarias": opiniao.condicoes_necessarias,
        "pendencias": opiniao.pendencias,
        "proximo_passo": opiniao.proximo_passo,
        "grau_certeza_leitura": opiniao.grau_certeza_leitura,
        "opcoes_esclarecimento": [
            _serializar_opcao(o) for o in opiniao.opcoes_esclarecimento
        ],
        "confirmada": row["confirmado_por"] is not None,
    }

# ============================================================
# GET /alertas + POST /alertas/{id}/lido
# ============================================================

def _serializar_alerta(r) -> dict:
    return {
        "id": str(r["id"]),
        "tipo": r["tipo"],
        "severidade": r["severidade"],
        "mensagem": r["mensagem"],
        "lido_em": r["lido_em"].isoformat() if r["lido_em"] else None,
        "criado_em": r["criado_em"].isoformat(),
        "banda_ou_slug": r["banda_ou_slug"],
        "prazo": r["prazo"].isoformat() if r["prazo"] else None,
    }


@router.get("/alertas")
async def listar_alertas_endpoint(
    request: Request,
    apenas_nao_lidos: bool = Query(False),
    tipo: str | None = Query(None),
    limite: int = Query(50, ge=1, le=500),
    cursor: str | None = Query(None),
    u: dict = Depends(usuario),
):
    async with conexao() as conn:
        rows, has_more, next_cursor = await listar_alertas(
            conn, _uuid.UUID(str(u["id"])),
            apenas_nao_lidos=apenas_nao_lidos,
            tipo=tipo,
            limite=limite,
            cursor=cursor,
        )
    return {
        "itens": [_serializar_alerta(r) for r in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.post("/alertas/{alerta_id}/lido")
async def marcar_alerta_lido_endpoint(
    alerta_id: str,
    u: dict = Depends(usuario),
):
    try:
        aid = _uuid.UUID(alerta_id)
    except ValueError:
        raise erro(400, "ID_INVALIDO", "ID do alerta invalido")

    async with conexao() as conn:
        resultado = await marcar_lido(conn, _uuid.UUID(str(u["id"])), aid)

    if resultado is None:
        raise erro(404, "ALERTA_NAO_ENCONTRADO", "Alerta nao encontrado")

    return {
        "alerta_id": alerta_id,
        "marcado_agora": resultado,
    }


# ============================================================
# GET /fiscal/resumo — leitura do estado fiscal
# ============================================================

@router.get("/fiscal/resumo")
async def fiscal_resumo_endpoint(
    u: dict = Depends(usuario),
):
    async with conexao() as conn:
        return await resumo_fiscal(conn, _uuid.UUID(str(u["id"])))

