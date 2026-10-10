"""Faturamento MEI — M4_CONTRATO §9 (soma) + §10 (alertas).

Decisoes documentadas nesta implementacao:

  M4b-D1  TETO_MEI_ANUAL = 81000.00
  M4b-D2  o faturamento e por ano-calendario
  M4b-D3  tipo="faturamento_faixa", banda_ou_slug="enq_MEI_NN",
          prazo=31/12 do ano de competencia

2026-10-09 — a soma do ano passou a ser DERIVADA dos lancamentos gravados
(M4_CONTRATO §9: "soma atual das transacoes do usuario em que ..."), em vez
de um contador ajustado por deltas. O contador se perdia quando chegava um
lancamento de outro ano: colar um extrato de 2025 depois de ja ter 2026
trocava o ano do painel e zerava o acumulado, e a soma de uma colagem que
atravessava a virada ia inteira para o ano mais novo. Agora:

  - `somar_faturamento_do_ano` le a soma de um ano direto de `transactions`
    (PRINCIPIOS §2: PostgreSQL como fonte de verdade);
  - `ano_de_referencia` e o ano mais recente com lancamento, sem passar do
    ano corrente;
  - cada escrita reavalia SO os anos que tocou, registra os alertas de faixa
    que faltarem para aquele ano (§10: "insere o alerta se ainda nao existir
    para aquele prazo") e regrava em `fiscal_state` o retrato do ano de
    referencia.

Estado JSONB em fiscal_state.estado (retrato da ultima avaliacao):
    {
      "faturamento_acumulado": "45000.00",
      "ano_referencia": 2026,
      "banda_atual": "enq_MEI_60",
      "ultima_avaliacao_em": "2026-09-27T..."
    }
O painel (services/fiscal_resumo.py) nao le o numero daqui: soma de novo.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import json

TETO_MEI_ANUAL = Decimal("81000.00")

# No ano de abertura o limite do MEI é proporcional: R$ 6.750 por mês de
# atividade, contando o mês de abertura (LC 123/2006, art. 18-A, §2º).
LIMITE_MEI_POR_MES = Decimal("6750.00")


def teto_do_ano(regime, mes_abertura, ano_abertura, ano_ref) -> Decimal | None:
    """Limite anual aplicável ao usuário, ou None quando não há limite de MEI.

    REGRA_ORIENTADOR §2.4: quem não é MEI não recebe o teto do MEI como
    "default silencioso".
    """
    if regime != "MEI":
        return None
    if mes_abertura and ano_abertura and int(ano_abertura) == int(ano_ref):
        meses_ativos = 12 - int(mes_abertura) + 1
        return LIMITE_MEI_POR_MES * meses_ativos
    return TETO_MEI_ANUAL


def mensagem_faixa(pct: Decimal, teto: Decimal, ano: int | None = None) -> str:
    """Texto do alerta, em linguagem simples e moeda brasileira."""
    from .rotulos import brl

    quando = f" de {ano}" if ano else ""
    limite = brl(teto)
    p = int(pct * 100)
    if p < 100:
        return (
            f"Seu faturamento como MEI{quando} chegou a {p}% do limite "
            f"anual ({limite})."
        )
    if p == 100:
        return (
            f"Seu faturamento como MEI{quando} passou do limite anual "
            f"({limite}). Acima do limite, as regras do MEI mudam — leve "
            f"estes números a um contador."
        )
    return (
        f"Seu faturamento como MEI{quando} passou de {p}% do limite anual "
        f"({limite}). Acima desse ponto as regras mudam de novo — leve "
        f"estes números a um contador."
    )

# (percentual, slug, severidade)
FAIXAS: tuple[tuple[Decimal, str, str], ...] = (
    (Decimal("0.60"), "enq_MEI_60",  "informativo"),
    (Decimal("0.80"), "enq_MEI_80",  "atencao"),
    (Decimal("0.90"), "enq_MEI_90",  "atencao"),
    (Decimal("0.95"), "enq_MEI_95",  "critico"),
    (Decimal("1.00"), "enq_MEI_100", "critico"),
    (Decimal("1.20"), "enq_MEI_120", "critico"),
)

TIPO_ALERTA = "faturamento_faixa"


def calcular_banda(
    faturamento: Decimal, teto: Decimal | None = TETO_MEI_ANUAL
) -> str | None:
    """Retorna o slug da maior faixa atingida, ou None se abaixo de 60%.

    Independe de direcao: subir ou descer, a banda e sempre a do valor
    atual. Alertas §10 continuam monotonico-crescentes — so cruzar
    para cima emite; a descida apenas recalcula esta banda.
    """
    if faturamento <= 0 or teto is None or teto <= 0:
        return None
    pct = faturamento / teto
    banda: str | None = None
    for p, slug, _ in FAIXAS:
        if pct >= p:
            banda = slug
    return banda


def conta_faturamento(
    patrimonio: str | None, categoria: str | None, valor=None
) -> bool:
    """Regra §9: so incrementa em atividade_negocio + receita_servico|venda.

    Quando `valor` e informado, saida (valor < 0) NUNCA conta: dinheiro que
    saiu da conta nao e faturamento, qualquer que seja a palavra-chave.
    """
    if valor is not None and Decimal(str(valor)) < 0:
        return False
    return (
        patrimonio == "atividade_negocio"
        and categoria in ("receita_servico", "receita_venda")
    )


def acumular_por_ano(deltas: dict[int, Decimal], quando: date, valor) -> None:
    """Soma `valor` ao delta do ano de `quando` (cada lancamento no seu ano)."""
    deltas[quando.year] = deltas.get(quando.year, Decimal("0")) + Decimal(str(valor))


# Espelho em SQL de `conta_faturamento`. Os dois precisam dizer a mesma coisa;
# tests/test_faturamento_por_ano.py compara um com o outro em todas as
# combinacoes de patrimonio, categoria e sinal.
_SQL_SOMA_DO_ANO = """
    SELECT COALESCE(SUM(valor), 0)
      FROM transactions
     WHERE user_id = $1
       AND data >= $2
       AND data <= $3
       AND valor > 0
       AND patrimonio = 'atividade_negocio'
       AND categoria IN ('receita_servico', 'receita_venda')
"""


async def somar_faturamento_do_ano(conn, user_id, ano: int) -> Decimal:
    """Soma, direto dos lancamentos gravados, do que conta no ano (§9)."""
    soma = await conn.fetchval(
        _SQL_SOMA_DO_ANO, user_id, date(ano, 1, 1), date(ano, 12, 31)
    )
    return Decimal(soma)


async def ano_de_referencia(conn, user_id, hoje: date | None = None) -> int:
    """Ano que o painel mostra: o mais recente com lancamento, sem passar do
    ano corrente. Sem lancamento nenhum, o ano corrente.

    Data no futuro (erro de digitacao num extrato, por exemplo) nao puxa o
    painel para um ano que ainda nao comecou.
    """
    hoje = hoje or date.today()
    ultima = await conn.fetchval(
        "SELECT MAX(data) FROM transactions WHERE user_id = $1 AND data <= $2",
        user_id,
        date(hoje.year, 12, 31),
    )
    return ultima.year if ultima is not None else hoje.year


def faixa_cruzada(
    antes: Decimal,
    depois: Decimal,
    teto: Decimal | None = TETO_MEI_ANUAL,
    ano: int | None = None,
) -> list[tuple[str, str, str]]:
    """Faixas cujo limiar foi cruzado no intervalo (antes, depois].

    Retorna [(slug, severidade, mensagem)] na ordem crescente das faixas.
    """
    cruzadas: list[tuple[str, str, str]] = []
    if teto is None:
        return cruzadas
    for pct, slug, sev in FAIXAS:
        limiar = teto * pct
        if antes < limiar <= depois:
            cruzadas.append((slug, sev, mensagem_faixa(pct, teto, ano)))
    return cruzadas


def prazo_do_ano(quando: date) -> date:
    """Prazo canonico: 31/12 do ano de competencia."""
    return date(quando.year, 12, 31)


@dataclass(frozen=True)
class FaturamentoResultado:
    antes: Decimal
    depois: Decimal
    ano_referencia: int
    faixas: tuple[tuple[str, str, str], ...]
    alertas_criados: tuple[tuple[str, str, str], ...] = ()


def calcular_delta(
    estado: dict,
    delta: Decimal,
    quando: date,
    teto: Decimal | None = TETO_MEI_ANUAL,
) -> tuple[dict, FaturamentoResultado]:
    """Retorna (novo_estado, resultado). Puro, sem I/O."""
    ano = quando.year
    estado = dict(estado)

    ano_ref = estado.get("ano_referencia")
    if ano_ref != ano:
        estado["faturamento_acumulado"] = "0"
        estado["ano_referencia"] = ano
        estado.pop("banda_atual", None)

    antes = Decimal(str(estado.get("faturamento_acumulado", "0")))
    depois = antes + delta

    estado["faturamento_acumulado"] = str(depois)
    estado["ultima_avaliacao_em"] = datetime.now(timezone.utc).isoformat()

    faixas = tuple(faixa_cruzada(antes, depois, teto, ano))
    # Recalcula banda_atual SEMPRE — descida tambem precisa refletir.
    # Alertas §10 seguem monotonico-crescentes (so faixa_cruzada emite).
    estado["banda_atual"] = calcular_banda(depois, teto)

    return estado, FaturamentoResultado(
        antes=antes,
        depois=depois,
        ano_referencia=ano,
        faixas=faixas,
    )


def _retrato(soma: Decimal, ano: int, teto: Decimal | None):
    """(estado, resultado) de um ano cuja soma e `soma`.

    Usa `calcular_delta` a partir de zero: `faixas` traz TODAS as faixas ja
    atingidas pela soma, e nao so as cruzadas pela ultima escrita. A tabela
    `alerts` e unica por (usuario, tipo, faixa, prazo), entao reavaliar nao
    duplica aviso — e um aviso que tenha faltado e registrado na proxima
    escrita do mesmo ano.
    """
    return calcular_delta(
        {"faturamento_acumulado": "0", "ano_referencia": ano},
        soma,
        date(ano, 12, 31),
        teto,
    )


async def atualizar_fiscal_state(
    conn, user_id, delta: Decimal, quando: date
) -> FaturamentoResultado:
    """Reavalia o faturamento do ano de `quando` e regrava fiscal_state.

    Chamar DEPOIS de gravar os lancamentos, na mesma transacao: a soma e
    lida do banco, nao acumulada. `delta` e o quanto a escrita mudou a soma
    daquele ano; com delta zero nada e reavaliado.

    Retorna alertas_criados: apenas os que foram efetivamente inseridos
    (ON CONFLICT DO NOTHING suprime duplicatas sem eco).
    """
    ano = quando.year

    if delta == 0:
        soma = await somar_faturamento_do_ano(conn, user_id, ano)
        return FaturamentoResultado(
            antes=soma, depois=soma, ano_referencia=ano, faixas=()
        )

    # Uma escrita por vez para cada usuario: quem chega depois so soma
    # quando a anterior ja confirmou, e por isso enxerga os lancamentos dela.
    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext($1))", f"fiscal_state:{user_id}"
    )

    # O limite depende de quem e o usuario: so MEI tem teto, e no ano de
    # abertura ele e proporcional. Quem nao e MEI nao recebe alerta de faixa.
    perfil = await conn.fetchrow(
        "SELECT regime, mes_abertura_mei, ano_abertura_mei "
        "FROM users WHERE id = $1",
        user_id,
    )

    def teto_de(ano_alvo: int) -> Decimal | None:
        if perfil is None:
            return TETO_MEI_ANUAL
        return teto_do_ano(
            perfil["regime"],
            perfil["mes_abertura_mei"],
            perfil["ano_abertura_mei"],
            ano_alvo,
        )

    soma = await somar_faturamento_do_ano(conn, user_id, ano)
    estado_do_ano, resultado = _retrato(soma, ano, teto_de(ano))

    ano_ref = await ano_de_referencia(conn, user_id)
    if ano_ref == ano:
        estado = estado_do_ano
    else:
        soma_ref = await somar_faturamento_do_ano(conn, user_id, ano_ref)
        estado, _ = _retrato(soma_ref, ano_ref, teto_de(ano_ref))

    await conn.execute(
        """
        INSERT INTO fiscal_state (user_id, estado, atualizado_em)
        VALUES ($1, $2::jsonb, now())
        ON CONFLICT (user_id) DO UPDATE
          SET estado = EXCLUDED.estado,
              atualizado_em = now()
        """,
        user_id,
        json.dumps(estado),
    )

    prazo = prazo_do_ano(quando)
    alertas_criados: list[tuple[str, str, str]] = []
    for slug, sev, msg in resultado.faixas:
        row = await conn.fetchval(
            """
            INSERT INTO alerts
              (user_id, tipo, banda_ou_slug, prazo, severidade, mensagem)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, tipo, banda_ou_slug, prazo)
              DO NOTHING
            RETURNING id
            """,
            user_id, TIPO_ALERTA, slug, prazo, sev, msg,
        )
        if row is not None:
            alertas_criados.append((slug, sev, msg))

    return FaturamentoResultado(
        antes=soma - delta,
        depois=soma,
        ano_referencia=ano,
        faixas=resultado.faixas,
        alertas_criados=tuple(alertas_criados),
    )


async def atualizar_fiscal_state_por_ano(
    conn, user_id, deltas_por_ano: Mapping[int, Decimal]
) -> tuple[tuple[str, str, str], ...]:
    """Reavalia cada ano que a escrita tocou, do mais antigo ao mais novo.

    Um extrato pode atravessar a virada do ano; cada lancamento entra na
    soma do ano da PROPRIA data. Retorna os alertas criados em todos os anos.
    """
    alertas: list[tuple[str, str, str]] = []
    for ano in sorted(deltas_por_ano):
        delta = deltas_por_ano[ano]
        if delta == 0:
            continue
        resultado = await atualizar_fiscal_state(
            conn, user_id, delta, date(ano, 12, 31)
        )
        alertas.extend(resultado.alertas_criados)
    return tuple(alertas)
