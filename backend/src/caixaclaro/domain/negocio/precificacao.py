"""Precificação — Categoria I da consulta ao CRC-ES (docs/CONSULTA_CRC_ES.md).

Cálculo puro sobre dado informado pelo usuário. Implementa exatamente
os quatro itens descritos na consulta institucional — nem mais, nem
menos, enquanto a resposta do conselho estiver pendente
(docs/REGRA_ORIENTADOR.md §7):

  1. Diferença entre preço e custo informado
  2. Margem de contribuição por unidade (R$ e %)
  3. Ponto de equilíbrio em unidades e em receita
  4. Comparação entre até dois cenários, lado a lado, sem indicar
     preferência (implementada na camada de serviço, que aceita até
     2 cenários nesta mesma função)

Nenhuma classificação automática de custo, nenhum rateio de custo
indireto, nenhuma conclusão sobre lucro ou saúde do negócio.

Decisão deliberada: `volume_hipotese` é aceito e devolvido como
HIPÓTESE registrada (para comparação futura com o resultado
observado — REGRA_ORIENTADOR.md §3, "comparar hipóteses... sem
julgamento sobre o acerto"), mas não é usado para derivar receita ou
lucro projetado nesta versão. Isso não está entre os quatro itens
descritos na consulta ao CRC-ES; ativar esse cálculo antes da
resposta do conselho seria avançar a fronteira sem orientação.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

DOIS_CASAS = Decimal("0.01")


class DadosInsuficientes(Exception):
    """O sistema se recusa a calcular — REGRA_ORIENTADOR.md §3, item 4
    das cinco perguntas de aceite: "pode se recusar a calcular e dizer
    'faltam dados' como resposta válida"."""

    def __init__(self, campo: str, motivo: str):
        self.campo = campo
        self.motivo = motivo
        super().__init__(f"{campo}: {motivo}")


@dataclass(frozen=True)
class Calculo:
    """Um resultado rotulado por estado, conforme REGRA_ORIENTADOR.md §1.

    estado é sempre "calculo" ou "limitacao" — nunca uma conclusão não
    rotulada. Quando estado="limitacao", `resultado` é None e
    `limitacao` explica o motivo.
    """

    nome: str
    formula: str
    variaveis: dict[str, str]
    resultado: str | None
    unidade: str
    estado: str
    limitacao: str | None = None


@dataclass(frozen=True)
class CenarioPrecificacao:
    nome: str
    hipoteses: dict[str, str]
    calculos: list[Calculo]
    limitacoes: list[str]


def _dec(valor, campo: str) -> Decimal:
    if valor is None:
        raise DadosInsuficientes(campo, "não foi informado")
    try:
        d = Decimal(str(valor))
    except InvalidOperation as e:
        raise DadosInsuficientes(campo, "não é um número válido") from e
    if d < 0:
        raise DadosInsuficientes(campo, "não pode ser negativo")
    return d


def calcular_cenario(
    *,
    nome: str,
    preco,
    custo_variavel_unitario,
    custos_fixos_periodo=None,
    volume_hipotese=None,
) -> CenarioPrecificacao:
    """Calcula os itens 1-3 da Categoria I para um único cenário.

    Nunca infere um valor ausente: cada entrada é HIPÓTESE informada
    pelo usuário (_dec levanta DadosInsuficientes quando falta ou é
    inválida). Quando falta o suficiente para um cálculo específico
    (ex.: custos_fixos_periodo para o ponto de equilíbrio), o item
    correspondente volta como LIMITAÇÃO, não como exceção — a recusa
    é parcial, não derruba o cenário inteiro.
    """
    preco_d = _dec(preco, "preco")
    custo_d = _dec(custo_variavel_unitario, "custo_variavel_unitario")

    hipoteses: dict[str, str] = {
        "preco": str(preco_d),
        "custo_variavel_unitario": str(custo_d),
    }

    calculos: list[Calculo] = []
    limitacoes: list[str] = []

    # --- Item 1: diferença entre preço e custo informado ---
    diferenca = preco_d - custo_d
    calculos.append(Calculo(
        nome="diferenca_preco_custo",
        formula="preco - custo_variavel_unitario",
        variaveis={"preco": str(preco_d), "custo_variavel_unitario": str(custo_d)},
        resultado=str(diferenca),
        unidade="R$",
        estado="calculo",
    ))

    # --- Item 2: margem de contribuição por unidade (R$ e %) ---
    calculos.append(Calculo(
        nome="margem_contribuicao_unitaria_reais",
        formula="preco - custo_variavel_unitario",
        variaveis={"preco": str(preco_d), "custo_variavel_unitario": str(custo_d)},
        resultado=str(diferenca),
        unidade="R$/unidade",
        estado="calculo",
    ))

    if preco_d == 0:
        limitacoes.append(
            "Margem de contribuição percentual não calculada: o preço "
            "informado é zero (divisão por zero)."
        )
        calculos.append(Calculo(
            nome="margem_contribuicao_unitaria_percentual",
            formula="(preco - custo_variavel_unitario) / preco * 100",
            variaveis={"preco": str(preco_d), "custo_variavel_unitario": str(custo_d)},
            resultado=None,
            unidade="%",
            estado="limitacao",
            limitacao="Preço informado é zero; percentual indeterminado.",
        ))
    else:
        margem_pct = (diferenca / preco_d) * 100
        calculos.append(Calculo(
            nome="margem_contribuicao_unitaria_percentual",
            formula="(preco - custo_variavel_unitario) / preco * 100",
            variaveis={"preco": str(preco_d), "custo_variavel_unitario": str(custo_d)},
            resultado=str(margem_pct.quantize(DOIS_CASAS)),
            unidade="%",
            estado="calculo",
        ))

    # --- Item 3: ponto de equilíbrio em unidades e em receita ---
    if custos_fixos_periodo is None:
        motivo = "Custos fixos do período não foram informados."
        limitacoes.append(f"Ponto de equilíbrio não calculado: {motivo.lower()}")
        for nome_calc, unidade in (
            ("ponto_equilibrio_unidades", "unidades"),
            ("ponto_equilibrio_receita", "R$"),
        ):
            calculos.append(Calculo(
                nome=nome_calc,
                formula="custos_fixos_periodo / margem_contribuicao_unitaria",
                variaveis={},
                resultado=None,
                unidade=unidade,
                estado="limitacao",
                limitacao=motivo,
            ))
    else:
        custos_fixos_d = _dec(custos_fixos_periodo, "custos_fixos_periodo")
        hipoteses["custos_fixos_periodo"] = str(custos_fixos_d)

        if diferenca <= 0:
            motivo = (
                "Margem de contribuição não é positiva com os valores "
                "informados (o preço não cobre o custo variável)."
            )
            limitacoes.append(f"Ponto de equilíbrio indeterminado: {motivo.lower()}")
            for nome_calc, unidade in (
                ("ponto_equilibrio_unidades", "unidades"),
                ("ponto_equilibrio_receita", "R$"),
            ):
                calculos.append(Calculo(
                    nome=nome_calc,
                    formula="custos_fixos_periodo / margem_contribuicao_unitaria",
                    variaveis={
                        "custos_fixos_periodo": str(custos_fixos_d),
                        "margem_contribuicao_unitaria": str(diferenca),
                    },
                    resultado=None,
                    unidade=unidade,
                    estado="limitacao",
                    limitacao=motivo,
                ))
        else:
            pe_unidades = custos_fixos_d / diferenca
            pe_receita = pe_unidades * preco_d
            calculos.append(Calculo(
                nome="ponto_equilibrio_unidades",
                formula="custos_fixos_periodo / margem_contribuicao_unitaria",
                variaveis={
                    "custos_fixos_periodo": str(custos_fixos_d),
                    "margem_contribuicao_unitaria": str(diferenca),
                },
                resultado=str(pe_unidades.quantize(DOIS_CASAS)),
                unidade="unidades",
                estado="calculo",
            ))
            calculos.append(Calculo(
                nome="ponto_equilibrio_receita",
                formula="ponto_equilibrio_unidades * preco",
                variaveis={
                    "ponto_equilibrio_unidades": str(pe_unidades.quantize(DOIS_CASAS)),
                    "preco": str(preco_d),
                },
                resultado=str(pe_receita.quantize(DOIS_CASAS)),
                unidade="R$",
                estado="calculo",
            ))

    if volume_hipotese is not None:
        volume_d = _dec(volume_hipotese, "volume_hipotese")
        hipoteses["volume_hipotese"] = str(volume_d)
        limitacoes.append(
            "O volume informado foi registrado como hipótese para "
            "comparação futura; não foi usado para projetar receita ou "
            "lucro nesta versão."
        )

    limitacoes.append(
        "Este cálculo não considera custos indiretos não informados, "
        "tributos, nem variação de demanda ao preço. Não é uma "
        "conclusão sobre lucro ou viabilidade do negócio."
    )

    return CenarioPrecificacao(
        nome=nome, hipoteses=hipoteses, calculos=calculos, limitacoes=limitacoes,
    )