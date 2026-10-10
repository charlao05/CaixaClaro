import base64
import binascii
import uuid as _uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..api.deps import usuario_ativo
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
    acumular_por_ano,
    atualizar_fiscal_state,
    atualizar_fiscal_state_por_ano,
    conta_faturamento,
)
from ..services.notificacoes import enviar_alertas_telegram
from ..services.fiscal import processar_lancamento
from ..services.tax_opinion import generate_tax_opinion
from ..services.fiscal_resumo import resumo as resumo_fiscal
from ..services.fila import (
    aplicar_a_iguais,
    carregar_regras,
    confirmar as confirmar_tx,
    lembrar_regra,
    listar_fila,
)
from ..services.rotulos import brl, opcoes_para, rotulo
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
        "proposito": r.get("proposito"),
        "rotulo": rotulo(r["categoria"], r.get("proposito")),
        "confirmada": r.get("confirmado_por") is not None,
        "needs_review": r["needs_review"],
        "criado_em": r["criado_em"].isoformat(),
        "atualizado_em": r["atualizado_em"].isoformat(),
        "versao": r["versao"],
    })
    return d


# ============================================================
# POST /extrato/colar
# ============================================================

async def _operacao_colar(conn, user_id: str, texto: str, alertas_out: list, regime: str):
    try:
        lancamentos = parse_texto(texto)
    except ExtratoIlegivel as e:
        raise erro(400, "EXTRATO_ILEGIVEL", str(e)) from e

    paste_id = calcular_paste_id(texto)
    uid = _uuid.UUID(user_id)
    importados = 0
    # Cada lançamento entra na soma do ano da própria data: um extrato pode
    # atravessar a virada do ano.
    deltas_por_ano: dict[int, Decimal] = {}
    ctx = ContextoClassificacao(
        personal_rules={},
        regime=regime,
        regras_pessoais=await carregar_regras(conn, _uuid.UUID(user_id)),
    )

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
            if conta_faturamento(c.patrimonio, cat, l.valor):
                acumular_por_ano(deltas_por_ano, l.data, l.valor)

    alertas_out.extend(
        await atualizar_fiscal_state_por_ano(conn, uid, deltas_por_ano)
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
    u: dict = Depends(usuario_ativo),
):
    alertas_para_enviar: list = []

    async def op(conn):
        return await _operacao_colar(
            conn, str(u["id"]), dados.texto, alertas_para_enviar,
            u["regime"],
        )

    resposta, status_http = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota="POST /api/v1/transacoes/extrato/colar",
        chave=idempotency_key,
        body=dados.model_dump(),
        operacao=op,
    )
    await enviar_alertas_telegram(u["id"], alertas_para_enviar)
    return JSONResponse(content=resposta, status_code=status_http)


# ============================================================
# POST /importar
# ============================================================

async def _operacao_importar(
    conn,
    user_id: str,
    formato: str,
    bruto: bytes,
    regime: str,
    alertas_out: list,
):
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
    # Cada lançamento entra na soma do ano da própria data: um extrato pode
    # atravessar a virada do ano.
    deltas_por_ano: dict[int, Decimal] = {}
    ctx = ContextoClassificacao(
        personal_rules={},
        regime=regime,
        regras_pessoais=await carregar_regras(conn, _uuid.UUID(user_id)),
    )

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
              (user_id, origem, import_id, line_index, data,
               descricao_bruta, valor,
               categoria, categoria_original,
               proposito, patrimonio, tratamento_tributario,
               confianca, needs_review, via, motivo)
            VALUES ($1, $2, $3, $4, $5, $6, $7,
                    $8, $8, $9, $10, $11, $12, $13, $14, $15)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            uid, formato, import_id, i, l.data, l.descricao, l.valor,
            cat, c.proposito, c.patrimonio, c.tratamento_tributario,
            c.confianca, rf.triagem.needs_review, c.via, c.motivo,
        )

        if inserted is not None:
            importados += 1

            if conta_faturamento(c.patrimonio, cat, l.valor):
                acumular_por_ano(deltas_por_ano, l.data, l.valor)

    alertas_out.extend(
        await atualizar_fiscal_state_por_ano(conn, uid, deltas_por_ano)
    )

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
    u: dict = Depends(usuario_ativo),
):
    try:
        bruto = base64.b64decode(dados.conteudo_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise erro(400, "ARQUIVO_ILEGIVEL", "Conteúdo base64 inválido.") from e
    if not bruto:
        raise erro(400, "ARQUIVO_ILEGIVEL", "Arquivo vazio.")

    alertas_para_enviar: list = []

    async def op(conn):
        return await _operacao_importar(
            conn,
            str(u["id"]),
            dados.formato,
            bruto,
            u["regime"],
            alertas_para_enviar,
        )

    resposta, status_http = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota="POST /api/v1/transacoes/importar",
        chave=idempotency_key,
        body=dados.model_dump(),
        operacao=op,
    )
    await enviar_alertas_telegram(u["id"], alertas_para_enviar)
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
    u: dict = Depends(usuario_ativo),
):
    uid = _uuid.UUID(str(u["id"]))
    cursor_data, cursor_id = (None, None)
    if cursor:
        cursor_data, cursor_id = _decode_cursor(cursor)

    sql = """
        SELECT id, data, descricao_bruta, valor, origem, line_index,
               categoria, proposito, confirmado_por,
               needs_review, criado_em, atualizado_em, versao
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
        "opcoes": list(opcoes_para(r["valor"])),
    }


@router.get("/fila")
async def fila(
    request: Request,
    limite: int = Query(50, ge=1, le=500),
    cursor: str | None = Query(None),
    u: dict = Depends(usuario_ativo),
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
    proposito: str | None = None
    # true => guarda a resposta como regra pessoal e aplica a mesma resposta
    # aos outros lancamentos pendentes com descricao e direcao iguais.
    lembrar: bool = False


@router.patch("/{tx_id}/confirmar")
async def confirmar_endpoint(
    tx_id: str,
    dados: ConfirmarIn,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    u: dict = Depends(usuario_ativo),
):
    alertas_para_enviar: list = []

    async def op(conn):
        return await _operacao_confirmar(
            conn, str(u["id"]), tx_id, dados.categoria, alertas_para_enviar,
            proposito=dados.proposito, lembrar=dados.lembrar,
            regime=u["regime"],
        )

    resposta, status_http = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota=f"PATCH /api/v1/transacoes/{tx_id}/confirmar",
        chave=idempotency_key,
        body={"tx_id": tx_id, **dados.model_dump()},
        operacao=op,
    )
    await enviar_alertas_telegram(u["id"], alertas_para_enviar)
    return JSONResponse(content=resposta, status_code=status_http)


_NOME_DA_SOMA = {
    "MEI": "do seu faturamento como MEI",
    "SIMPLES": "das receitas do seu negócio",
    "PF": "do que você recebeu por trabalho",
}


def _mensagem_confirmacao(resultado, iguais, regra_criada, regime, delta_total) -> str:
    """Resposta em linguagem de gente para a decisão do usuário."""
    soma = _NOME_DA_SOMA.get(regime, _NOME_DA_SOMA["MEI"])
    nome = rotulo(resultado.categoria_nova, resultado.proposito_novo)
    partes = [f"Anotado: {nome[0].lower()}{nome[1:]}."]
    if delta_total > 0:
        partes.append(f"Entrou na soma {soma} (+{brl(delta_total)}).")
    elif delta_total < 0:
        partes.append(f"Saiu da soma {soma} (−{brl(delta_total)}).")
    else:
        partes.append(f"Não muda a soma {soma}.")
    if iguais:
        n = len(iguais)
        partes.append(
            "A mesma resposta valeu para mais 1 lançamento igual."
            if n == 1
            else f"A mesma resposta valeu para mais {n} lançamentos iguais."
        )
    if regra_criada:
        partes.append(
            "Quando aparecer outro igual, o CaixaClaro já usa esta resposta."
        )
    return " ".join(partes)


async def _operacao_confirmar(
    conn, user_id, tx_id, categoria_nova, alertas_out,
    *, proposito=None, lembrar=False, regime="MEI", corrigir=False,
):
    try:
        tx_uuid = _uuid.UUID(tx_id)
    except ValueError:
        raise erro(400, "ID_INVALIDO", "ID da transação inválido")

    uid = _uuid.UUID(user_id)
    resultado, motivo = await confirmar_tx(
        conn, uid, tx_uuid, categoria_nova, user_id,
        proposito_novo=proposito, permitir_correcao=corrigir,
    )

    if resultado is None:
        if motivo == "nao_encontrada":
            raise erro(404, "TX_NAO_ENCONTRADA", "Transação não encontrada")
        if motivo == "ja_confirmada":
            raise erro(409, "JA_CONFIRMADA", "Transação já foi confirmada")
        if motivo == "nao_esta_em_revisao":
            raise erro(
                409, "NAO_EM_REVISAO",
                "Transação não está em fila de revisão",
            )
        if motivo == "categoria_invalida":
            raise erro(
                400, "CATEGORIA_INVALIDA",
                f"Categoria desconhecida: {categoria_nova}",
            )
        if motivo == "proposito_invalido":
            raise erro(
                400, "PROPOSITO_INVALIDO",
                f"Propósito desconhecido: {proposito}",
            )
        raise erro(500, "ERRO_INTERNO", "Motivo desconhecido")

    iguais = []
    regra_criada = False
    if lembrar:
        iguais = await aplicar_a_iguais(conn, uid, resultado, user_id)
        regra_criada = await lembrar_regra(conn, uid, resultado)

    # Retroatividade (M4_CONTRATO §9): cada decisão muda a soma do ano do
    # próprio lançamento. A soma é relida do banco, um ano de cada vez.
    deltas_por_ano: dict[int, Decimal] = {}
    delta_total = Decimal("0")
    for r in [resultado, *iguais]:
        if r.delta_faturamento != 0:
            acumular_por_ano(deltas_por_ano, r.data, r.delta_faturamento)
            delta_total += r.delta_faturamento
    alertas_out.extend(
        await atualizar_fiscal_state_por_ano(conn, uid, deltas_por_ano)
    )

    await registrar_auditoria(
        conn,
        ator="usuario",
        acao="transacao_corrigida" if corrigir else "transacao_confirmada",
        user_id=user_id,
        meta={
            "tx_id": tx_id,
            "categoria_antiga": resultado.categoria_antiga,
            "categoria_nova": resultado.categoria_nova,
            "proposito": resultado.proposito_novo,
            "delta_faturamento": str(resultado.delta_faturamento),
            "lembrar": lembrar,
            "aplicadas_iguais": len(iguais),
            "regra_criada": regra_criada,
        },
    )

    return {
        "tx_id": resultado.tx_id,
        "categoria_antiga": resultado.categoria_antiga,
        "categoria_nova": resultado.categoria_nova,
        "proposito": resultado.proposito_novo,
        "rotulo": rotulo(resultado.categoria_nova, resultado.proposito_novo),
        "delta_faturamento": str(resultado.delta_faturamento),
        "delta_total": str(delta_total),
        "categoria_mudou": resultado.categoria_mudou,
        "conta_no_faturamento": resultado.conta_no_faturamento,
        "aplicadas_iguais": len(iguais),
        "ids_aplicados": [r.tx_id for r in iguais],
        "regra_criada": regra_criada,
        "mensagem": _mensagem_confirmacao(
            resultado, iguais, regra_criada, regime, delta_total
        ),
    }, 200


# ============================================================
# PATCH /transacoes/{id}/corrigir — o usuário sempre pode corrigir
# ============================================================

class CorrigirIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categoria: str
    proposito: str | None = None
    lembrar: bool = False


@router.patch("/{tx_id}/corrigir")
async def corrigir_endpoint(
    tx_id: str,
    dados: CorrigirIn,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    u: dict = Depends(usuario_ativo),
):
    """Corrige qualquer lançamento do usuário — inclusive um que a máquina
    classificou em silêncio ou que ele mesmo confirmou errado. Sem isto, um
    palpite errado ficava sem conserto (confirmar devolvia 409)."""
    alertas_para_enviar: list = []

    async def op(conn):
        return await _operacao_confirmar(
            conn, str(u["id"]), tx_id, dados.categoria, alertas_para_enviar,
            proposito=dados.proposito, lembrar=dados.lembrar,
            regime=u["regime"], corrigir=True,
        )

    resposta, status_http = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota=f"PATCH /api/v1/transacoes/{tx_id}/corrigir",
        chave=idempotency_key,
        body={"tx_id": tx_id, **dados.model_dump()},
        operacao=op,
    )
    await enviar_alertas_telegram(u["id"], alertas_para_enviar)
    return JSONResponse(content=resposta, status_code=status_http)


# ============================================================
# GET /transacoes/opcoes-resposta — vocabulário único (M8: "centralizar
# taxonomia via endpoint" era follow-up registrado)
# ============================================================

@router.get("/opcoes-resposta")
async def opcoes_resposta(u: dict = Depends(usuario_ativo)):
    return {
        "entrada": list(opcoes_para(Decimal("1"))),
        "saida": list(opcoes_para(Decimal("-1"))),
    }


# ============================================================
# POST /transacoes/manual — anotar um lançamento sem extrato
# ============================================================

class ManualIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: date
    descricao: str = Field(min_length=1, max_length=200)
    # String decimal com sinal: positivo = entrou, negativo = saiu.
    valor: str = Field(min_length=1, max_length=20)
    categoria: str | None = None
    proposito: str | None = None


@router.post("/manual", status_code=201)
async def manual(
    dados: ManualIn,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    u: dict = Depends(usuario_ativo),
):
    """Quem recebe em dinheiro, ou ainda não tem extrato organizado, também
    precisa conseguir começar. A origem `manual` já existia no contrato
    (CONTRATOS_INTERNOS §3) e no schema, mas não tinha rota."""
    try:
        valor = Decimal(dados.valor)
    except InvalidOperation:
        raise erro(422, "VALIDATION_ERROR", "Valor inválido.")
    if not valor.is_finite() or valor == 0:
        raise erro(422, "VALIDATION_ERROR", "Informe um valor diferente de zero.")
    valor = valor.quantize(Decimal("0.01"))
    if dados.data > date.today():
        raise erro(422, "VALIDATION_ERROR", "A data não pode estar no futuro.")
    descricao = dados.descricao.strip()
    if not descricao:
        raise erro(422, "VALIDATION_ERROR", "Descreva o lançamento.")

    alertas_para_enviar: list = []

    async def op(conn):
        uid = _uuid.UUID(str(u["id"]))
        ctx = ContextoClassificacao(
            personal_rules={},
            regime=u["regime"],
            regras_pessoais=await carregar_regras(conn, uid),
        )
        rf = processar_lancamento(descricao, valor, contexto=ctx)
        cat = rf.guardrail.categoria_corrigida
        c = rf.classificacao
        tx_id = await conn.fetchval(
            """
            INSERT INTO transactions
              (user_id, origem, data, descricao_bruta, valor,
               categoria, categoria_original,
               proposito, patrimonio, tratamento_tributario,
               confianca, needs_review, via, motivo)
            VALUES ($1, 'manual', $2, $3, $4,
                    $5, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            uid, dados.data, descricao, valor,
            cat, c.proposito, c.patrimonio, c.tratamento_tributario,
            c.confianca, rf.triagem.needs_review, c.via, c.motivo,
        )
        delta = valor if conta_faturamento(c.patrimonio, cat, valor) else Decimal("0")

        if dados.categoria is not None:
            resultado, motivo = await confirmar_tx(
                conn, uid, tx_id, dados.categoria, str(u["id"]),
                proposito_novo=dados.proposito, permitir_correcao=True,
            )
            if resultado is None:
                codigo = (
                    "PROPOSITO_INVALIDO" if motivo == "proposito_invalido"
                    else "CATEGORIA_INVALIDA"
                )
                raise erro(400, codigo, "Tipo de lançamento desconhecido.")
            delta += resultado.delta_faturamento

        if delta != 0:
            res = await atualizar_fiscal_state(conn, uid, delta, dados.data)
            alertas_para_enviar.extend(res.alertas_criados)

        row = await conn.fetchrow(
            """
            SELECT id, data, descricao_bruta, valor, origem, line_index,
                   categoria, proposito, confirmado_por,
                   needs_review, criado_em, atualizado_em, versao
              FROM transactions WHERE id = $1
            """,
            tx_id,
        )
        await registrar_auditoria(
            conn,
            ator="usuario",
            acao="lancamento_manual",
            user_id=str(u["id"]),
            meta={"tx_id": str(tx_id), "informou_categoria": dados.categoria is not None},
        )
        return _serializar_completa(row), 201

    resposta, status_http = await executar_com_idempotencia(
        user_id=str(u["id"]),
        rota="POST /api/v1/transacoes/manual",
        chave=idempotency_key,
        body=dados.model_dump(mode="json"),
        operacao=op,
    )
    await enviar_alertas_telegram(u["id"], alertas_para_enviar)
    return JSONResponse(content=resposta, status_code=status_http)


# ============================================================
# GET /transacoes/{tx_id}/opiniao — CONTRATOS_INTERNOS §6
# ============================================================

def _serializar_opcao(o) -> dict:
    return {
        "label": o.label,
        "proposito": o.proposito,
        "categoria": o.categoria,
        "descricao": o.descricao,
    }


@router.get("/{tx_id}/opiniao")
async def opiniao_endpoint(
    tx_id: str,
    u: dict = Depends(usuario_ativo),
):
    async with conexao() as conn:
        return await _operacao_opiniao(conn, str(u["id"]), tx_id)


async def _operacao_opiniao(conn, user_id, tx_id):
    try:
        tx_uuid = _uuid.UUID(tx_id)
    except ValueError:
        raise erro(400, "ID_INVALIDO", "ID da transação inválido")

    row = await conn.fetchrow(
        """
        SELECT t.data, t.descricao_bruta, t.valor, t.categoria, t.categoria_original,
               t.proposito, t.patrimonio, t.tratamento_tributario,
               t.confianca, t.needs_review, t.via, t.confirmado_por,
               u.regime
          FROM transactions t
          JOIN users u ON u.id = t.user_id
         WHERE t.id = $1 AND t.user_id = $2
        """,
        tx_uuid,
        _uuid.UUID(user_id),
    )
    if row is None:
        raise erro(404, "TX_NAO_ENCONTRADA", "Transação não encontrada")

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

    # A regra de proteção acionada na ingestão não é persistida; não se
    # reconstrói um "guardrail aplicado" a partir de categoria diferente da
    # original — isso é o usuário corrigindo, não uma regra da máquina.
    cat_orig = row["categoria_original"] or cat_atual
    confirmada = row["confirmado_por"] is not None
    guard = GuardrailResultado(
        aplicado=False,
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
        regime=row["regime"] or "MEI",
        confirmada=confirmada,
    )

    return {
        "tx_id": tx_id,
        "data": row["data"].isoformat(),
        "descricao": row["descricao_bruta"],
        "valor": str(row["valor"]),
        "rotulo": rotulo(cat_atual, row["proposito"]),
        "opcoes_correcao": list(opcoes_para(row["valor"])),
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
        "confirmada": confirmada,
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
    u: dict = Depends(usuario_ativo),
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
    u: dict = Depends(usuario_ativo),
):
    try:
        aid = _uuid.UUID(alerta_id)
    except ValueError:
        raise erro(400, "ID_INVALIDO", "ID do alerta inválido")

    async with conexao() as conn:
        resultado = await marcar_lido(conn, _uuid.UUID(str(u["id"])), aid)

    if resultado is None:
        raise erro(404, "ALERTA_NAO_ENCONTRADO", "Alerta não encontrado")

    return {
        "alerta_id": alerta_id,
        "marcado_agora": resultado,
    }


# ============================================================
# GET /fiscal/resumo — leitura do estado fiscal
# ============================================================

@router.get("/fiscal/resumo")
async def fiscal_resumo_endpoint(
    u: dict = Depends(usuario_ativo),
):
    async with conexao() as conn:
        return await resumo_fiscal(conn, _uuid.UUID(str(u["id"])))

