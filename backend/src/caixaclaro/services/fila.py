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

import json

from ..domain.fiscal.classificacao import (
    PROPOSITOS_VALIDOS,
    ContextoClassificacao,
    RegraPessoal,
    dimensoes_padrao,
    normalizar_descricao,
)
from ..domain.fiscal.taxonomia import get_categoria
from .faturamento import conta_faturamento
from .fiscal import processar_lancamento


def _delta_faturamento(
    categoria_antiga: str,
    categoria_nova: str,
    patrimonio: str | None,
    valor: Decimal,
) -> Decimal:
    """Delta retroativo. Zero quando a mudanca nao toca §9."""
    antes = valor if conta_faturamento(patrimonio, categoria_antiga, valor) else Decimal("0")
    depois = valor if conta_faturamento(patrimonio, categoria_nova, valor) else Decimal("0")
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
        SELECT id, user_id, data, descricao_bruta, valor,
               categoria, categoria_original, proposito, patrimonio,
               tratamento_tributario, needs_review, confirmado_por
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
    proposito_novo: str | None = None
    valor: Decimal = Decimal("0")
    data: date | None = None
    descricao: str = ""
    conta_no_faturamento: bool = False


async def _gravar_decisao(conn, row, cat_nova: str, proposito_novo: str | None,
                          confirmado_por) -> ConfirmacaoResultado:
    """Grava a decisao do usuario em uma transacao ja travada (FOR UPDATE).

    CONTRATOS_INTERNOS §15: categoria e proposito sao do usuario. As demais
    dimensoes (patrimonio, tratamento) ACOMPANHAM a decisao dele — antes
    ficavam presas ao palpite original, e por isso uma entrada confirmada
    como trabalho nunca entrava no faturamento (M4_CONTRATO §9 diz que
    "outra categoria -> receita PJ: ADICIONA o valor").
    """
    cat_antiga = row["categoria"] or "outros"
    patr_antigo = row["patrimonio"]
    valor = row["valor"]

    manter = (
        cat_nova == cat_antiga
        and proposito_novo is None
        and row["proposito"] is not None
        and patr_antigo is not None
    )
    if manter:
        proposito = row["proposito"]
        patrimonio = patr_antigo
        tratamento = row["tratamento_tributario"]
    else:
        proposito, _origem, patrimonio, tratamento = dimensoes_padrao(
            cat_nova, proposito_novo
        )

    antes = valor if conta_faturamento(patr_antigo, cat_antiga, valor) else Decimal("0")
    conta = conta_faturamento(patrimonio, cat_nova, valor)
    depois = valor if conta else Decimal("0")
    delta = Decimal(depois) - Decimal(antes)

    await conn.execute(
        """
        UPDATE transactions
           SET categoria = $1,
               proposito = $2,
               patrimonio = $3,
               tratamento_tributario = $4,
               needs_review = false,
               via = 'usuario',
               confirmado_por = $5,
               confirmado_em = now(),
               versao = versao + 1,
               atualizado_em = now()
         WHERE id = $6
        """,
        cat_nova, proposito, patrimonio, tratamento, confirmado_por, row["id"],
    )

    return ConfirmacaoResultado(
        tx_id=str(row["id"]),
        categoria_antiga=cat_antiga,
        categoria_nova=cat_nova,
        delta_faturamento=delta,
        categoria_mudou=(cat_antiga != cat_nova),
        proposito_novo=proposito,
        valor=valor,
        data=row["data"],
        descricao=row["descricao_bruta"],
        conta_no_faturamento=conta,
    )


async def confirmar(
    conn,
    user_id,
    tx_id,
    categoria_nova: str | None,
    confirmado_por: str,
    proposito_novo: str | None = None,
    permitir_correcao: bool = False,
):
    """Confirma (ou corrige) uma transacao. Retorna (ConfirmacaoResultado, None)
    ou (None, motivo).

    Sem `permitir_correcao`, vale o contrato M5A: so transacao da fila e
    ainda nao confirmada. Com ele, o usuario pode corrigir qualquer
    lancamento seu — inclusive um que a maquina classificou em silencio ou
    que ele mesmo confirmou errado.
    """
    row = await buscar_para_confirmar(conn, user_id, tx_id)
    if row is None:
        return None, "nao_encontrada"

    if not permitir_correcao:
        if row["confirmado_por"] is not None:
            return None, "ja_confirmada"
        if not row["needs_review"]:
            return None, "nao_esta_em_revisao"

    cat_nova = categoria_nova or row["categoria"] or "outros"
    try:
        get_categoria(cat_nova)
    except KeyError:
        return None, "categoria_invalida"

    if proposito_novo is not None and proposito_novo not in PROPOSITOS_VALIDOS:
        return None, "proposito_invalido"

    resultado = await _gravar_decisao(
        conn, row, cat_nova, proposito_novo, confirmado_por
    )
    return resultado, None


# ============================================================
# Aprender com a resposta do usuario
# ============================================================

TAMANHO_MINIMO_PADRAO = 8


def _direcao(valor) -> str:
    return "saida" if Decimal(str(valor)) < 0 else "entrada"


async def aplicar_a_iguais(
    conn, user_id, referencia: ConfirmacaoResultado, confirmado_por
) -> list[ConfirmacaoResultado]:
    """Aplica a mesma resposta aos outros lancamentos pendentes com a MESMA
    descricao e a MESMA direcao. So roda quando o usuario pediu para lembrar.
    """
    alvo = normalizar_descricao(referencia.descricao)
    direcao = _direcao(referencia.valor)
    rows = await conn.fetch(
        """
        SELECT id, user_id, data, descricao_bruta, valor,
               categoria, categoria_original, proposito, patrimonio,
               tratamento_tributario, needs_review, confirmado_por
          FROM transactions
         WHERE user_id = $1
           AND needs_review = true
           AND confirmado_por IS NULL
           AND id <> $2
         ORDER BY data, id
         FOR UPDATE
        """,
        user_id,
        _uuid.UUID(referencia.tx_id),
    )
    aplicados: list[ConfirmacaoResultado] = []
    for row in rows:
        if normalizar_descricao(row["descricao_bruta"]) != alvo:
            continue
        if _direcao(row["valor"]) != direcao:
            continue
        aplicados.append(
            await _gravar_decisao(
                conn, row, referencia.categoria_nova,
                referencia.proposito_novo, confirmado_por,
            )
        )
    return aplicados


def _regra_dispensa_pergunta(regra: RegraPessoal, referencia: ConfirmacaoResultado) -> bool:
    """A regra só é guardada se, na próxima vez, ela de fato evitar a pergunta.

    Há lançamentos que o CaixaClaro pergunta sempre, por regra de proteção
    (retirada do negócio para o dono, descrição com cara de imposto). Guardar
    a resposta nesses casos faria a tela prometer "quando aparecer outro
    igual, o CaixaClaro já usa esta resposta" e perguntar de novo mesmo assim.
    """
    resultado = processar_lancamento(
        referencia.descricao,
        referencia.valor,
        contexto=ContextoClassificacao(personal_rules={}, regras_pessoais=(regra,)),
    )
    return (
        resultado.classificacao.via == "regra_personalizada"
        and resultado.guardrail.categoria_corrigida == regra.categoria
        and not resultado.triagem.needs_review
    )


async def lembrar_regra(conn, user_id, referencia: ConfirmacaoResultado) -> bool:
    """Guarda a resposta como regra pessoal (M4_CONTRATO §5, precedência 1).

    Não cria regra para descrição curta demais (casaria com quase tudo), para
    `outros` (a triagem mandaria de volta para a fila de qualquer jeito) nem
    quando uma regra de proteção faria o CaixaClaro perguntar de novo.
    """
    padrao = normalizar_descricao(referencia.descricao)
    if len(padrao) < TAMANHO_MINIMO_PADRAO:
        return False
    if referencia.categoria_nova == "outros":
        return False
    direcao = _direcao(referencia.valor)
    regra = RegraPessoal(
        padrao=padrao,
        categoria=referencia.categoria_nova,
        proposito=referencia.proposito_novo,
        direcao=direcao,
    )
    if not _regra_dispensa_pergunta(regra, referencia):
        return False
    # Uma regra por (padrão, direção): a resposta nova substitui a anterior
    # do MESMO sentido e convive com a do sentido oposto. Regra antiga sem
    # direção valia para os dois sentidos; a resposta nova a substitui.
    await conn.execute(
        """
        DELETE FROM personal_rules
         WHERE user_id = $1
           AND regra->>'padrao' = $2
           AND (regra->>'direcao' = $3 OR regra->>'direcao' IS NULL)
        """,
        user_id, padrao, direcao,
    )
    await conn.execute(
        "INSERT INTO personal_rules (user_id, regra) VALUES ($1, $2::jsonb)",
        user_id,
        json.dumps({
            "padrao": padrao,
            "categoria": referencia.categoria_nova,
            "proposito": referencia.proposito_novo,
            "direcao": direcao,
        }),
    )
    return True


async def carregar_regras(conn, user_id) -> tuple[RegraPessoal, ...]:
    """Regras pessoais do usuário, na ordem em que devem ser avaliadas.

    Padrões mais longos primeiro, para o mais específico vencer; entre
    padrões do mesmo tamanho, a resposta mais recente vem antes.

    Cada regra carrega a direção (entrada/saída) do lançamento em que foi
    aprendida, e `classificar_v2` só a aplica a lançamentos do mesmo sentido.
    """
    rows = await conn.fetch(
        "SELECT regra FROM personal_rules WHERE user_id = $1 "
        "ORDER BY criado_em DESC, id DESC",
        user_id,
    )
    regras: list[RegraPessoal] = []
    for r in rows:
        bruto = r["regra"]
        dado = json.loads(bruto) if isinstance(bruto, str) else dict(bruto)
        if not (dado.get("padrao") and dado.get("categoria")):
            continue
        direcao = dado.get("direcao")
        regras.append(RegraPessoal(
            padrao=dado["padrao"],
            categoria=dado["categoria"],
            proposito=dado.get("proposito") or None,
            direcao=direcao if direcao in ("entrada", "saida") else None,
        ))
    # sort é estável: preserva "mais recente primeiro" entre tamanhos iguais.
    regras.sort(key=lambda regra: len(regra.padrao), reverse=True)
    return tuple(regras)
