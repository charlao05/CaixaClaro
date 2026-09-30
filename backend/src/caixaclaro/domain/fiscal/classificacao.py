"""Classificação determinística — CONTRATOS_INTERNOS §4 + M4_CONTRATO §5.

Precedência:
  1. personal_rules  (via='regra_personalizada')
  2. heurística      (via='heuristica')
  3. fallback        (via='heuristica', categoria='outros', needs_review=True)

Guardrail CPF (§6) e triagem (§7) são aplicados em módulos separados,
depois do retorno desta função.

NOTA: os valores de `proposito` usados aqui não estão enumerados em
CONTRATOS_INTERNOS. Precisam ser congelados em §4.2 antes de M4a fechar.
A lista corrente (11 valores) está em `PropositoId`.
"""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .taxonomia import CategoriaId


PropositoId = Literal[
    "trabalho_servico",
    "venda_produto",
    "salario_aposentadoria",
    "transferencia_propria",
    "retirada_proprietario",
    "emprestimo",
    "devolucao_reembolso",
    "gasto_negocio",
    "gasto_pessoal",
    "imposto_taxa",
    "outros_indeterminado",
    "aporte_capital",
    "dinheiro_terceiros",
    "rendimento_aplicacao",
    "doacao_heranca",
]

OrigemSugeridaId = Literal[
    "empresa_contratante",
    "cliente_pf",
    "conta_propria",
    "amigo_familiar",
    "banco_financeira",
    "governo_orgao",
    "desconhecido",
]

PatrimonioId = Literal[
    "pessoa_fisica",
    "atividade_negocio",
    "ponte_pf_pj",
    "transito_terceiro",
]

TratamentoTributarioId = Literal[
    "tributavel_irpf",
    "isento_nao_tributavel",
    "carne_leao_potencial",
    "faturamento_pj",
    "retencao_fonte",
    "indeterminado_pendente",
]

ViaId = Literal["regra_personalizada", "heuristica", "guardrail", "usuario"]


@dataclass(frozen=True)
class ContextoClassificacao:
    personal_rules: dict[str, str]
    cpf_titular_hash: str | None = None
    cpf_contraparte_hash: str | None = None
    tipo_conta: str | None = None
    regime: str = "MEI"


@dataclass(frozen=True)
class ClassificacaoResultado:
    categoria: CategoriaId
    proposito: PropositoId
    origem_sugerida: OrigemSugeridaId
    patrimonio: PatrimonioId
    tratamento_tributario: TratamentoTributarioId
    confianca: float
    needs_review: bool
    via: ViaId
    motivo: str | None


_DEFAULTS = {
    "receita_servico":       ("trabalho_servico",      "empresa_contratante", "atividade_negocio", "tributavel_irpf"),
    "receita_venda":         ("venda_produto",         "cliente_pf",          "atividade_negocio", "faturamento_pj"),
    "salario":               ("salario_aposentadoria", "empresa_contratante", "pessoa_fisica",     "retencao_fonte"),
    "imposto_das":           ("imposto_taxa",          "governo_orgao",       "atividade_negocio", "isento_nao_tributavel"),
    "taxas_tarifas":         ("imposto_taxa",          "banco_financeira",    "atividade_negocio", "isento_nao_tributavel"),
    "custo_operacional":     ("gasto_negocio",         "desconhecido",        "atividade_negocio", "indeterminado_pendente"),
    "transferencia_propria": ("transferencia_propria", "conta_propria",       "pessoa_fisica",     "isento_nao_tributavel"),
    "pessoal_prolabore":     ("retirada_proprietario", "empresa_contratante", "ponte_pf_pj",       "indeterminado_pendente"),
    "reembolso":             ("devolucao_reembolso",   "desconhecido",        "pessoa_fisica",     "isento_nao_tributavel"),
    "emprestimo":            ("emprestimo",            "banco_financeira",    "pessoa_fisica",     "isento_nao_tributavel"),
    "outros":                ("outros_indeterminado",  "desconhecido",        "pessoa_fisica",     "indeterminado_pendente"),
}

_PROP_OVERRIDES = {
    "aporte_capital":       ("conta_propria",    "ponte_pf_pj",       "isento_nao_tributavel"),
    "dinheiro_terceiros":   ("desconhecido",     "transito_terceiro", "isento_nao_tributavel"),
    "rendimento_aplicacao": ("banco_financeira", "pessoa_fisica",     "tributavel_irpf"),
    "doacao_heranca":       ("amigo_familiar",   "pessoa_fisica",     "isento_nao_tributavel"),
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _contem(norm: str, *termos: str) -> bool:
    return any(t in norm for t in termos)


def _montar(cat, *, via, confianca, needs_review, motivo=None, proposito=None):
    prop, orig, patr, trat = _DEFAULTS[cat]
    if proposito is not None:
        prop = proposito
        if proposito in _PROP_OVERRIDES:
            orig, patr, trat = _PROP_OVERRIDES[proposito]
    return ClassificacaoResultado(
        categoria=cat,
        proposito=proposito if proposito is not None else prop,
        origem_sugerida=orig,
        patrimonio=patr,
        tratamento_tributario=trat,
        confianca=confianca,
        needs_review=needs_review,
        via=via,
        motivo=motivo,
    )


def _heuristica(norm, ctx):
    # M8-D3: propósitos estendidos — precedência antes das heurísticas atuais.
    if _contem(norm, "aporte de capital", "aporte capital",
               "integralizacao de capital", "integralizacao capital",
               "capital social",
               "subscricao de capital", "aumento de capital"):
        return _montar("outros", via="heuristica", confianca=0.90,
                       needs_review=True, proposito="aporte_capital",
                       motivo="Aporte de capital identificado por padrao textual.")

    if _contem(norm, "dinheiro de terceiro", "dinheiro de terceiros",
               "valor de terceiro", "valor de terceiros",
               "valor a repassar", "valor para repasse",
               "repasse de terceiro", "repasse para terceiro",
               "caucao",
               "adiantamento de terceiro", "adiantamento de terceiros"):
        return _montar("outros", via="heuristica", confianca=0.80,
                       needs_review=True, proposito="dinheiro_terceiros",
                       motivo="Possivel recurso de terceiro identificado.")

    if _contem(norm, "doacao recebida",
               "recebimento de doacao",
               "heranca", "recebimento de heranca",
               "legado", "legado recebido",
               "meacao recebida",
               "transmissao por heranca"):
        return _montar("outros", via="heuristica", confianca=0.90,
                       needs_review=True, proposito="doacao_heranca",
                       motivo="Transmissao patrimonial identificada.")

    if _contem(norm, "rendimento cdb", "rendimento tesouro",
               "rendimento tesouro direto",
               "rendimento poupanca", "rendimento fundo",
               "rendimento aplicacao", "rendimento financeiro",
               "rendimento de aplicacao",
               "dividendos",
               "juros sobre capital", "juros sobre capital proprio"):
        return _montar("outros", via="heuristica", confianca=0.90,
                       needs_review=True, proposito="rendimento_aplicacao",
                       motivo="Rendimento financeiro identificado.")

    if _contem(norm, "das simples", "das mei", "pgmei", "darf", "carne leao", "gps inss",
               "arrecadacao receita federal"):
        return _montar("imposto_das", via="heuristica", confianca=0.98,
                       needs_review=False,
                       motivo="Tributo identificado por padrão textual.")

    if _contem(norm, "salario", "folha pagto", "inss benef", "beneficio inss",
               "vencimentos"):
        return _montar("salario", via="heuristica", confianca=0.98,
                       needs_review=False)

    if _contem(norm, "emprestimo", "financiamento", "credito pessoal",
               "mutuo", "consignado"):
        return _montar("emprestimo", via="heuristica", confianca=0.95,
                       needs_review=False,
                       motivo="Recurso temporário, não compõe renda.")

    if _contem(norm, "estorno", "devolucao", "reembolso", "ressarcimento"):
        return _montar("reembolso", via="heuristica", confianca=0.95,
                       needs_review=False,
                       motivo="Devolução de valor anteriormente desembolsado.")
    # 2.5 transferencia propria textual -- exceto quando ha sinal forte
    # de tarifa na mesma descricao (ex.: IOF RESGATE POUPANCA e tarifa).
    SINAL_FORTE_TARIFA = ("iof", "tarifa", "mdr", "taxa manutencao",
                          "taxa extrato", "taxa liquidacao")
    if not _contem(norm, *SINAL_FORTE_TARIFA):
        if _contem(norm, "minha poupanca", "mesma titularidade", "minha conta",
                   "resgate poupanca", "aplicacao poupanca"):
            return _montar("transferencia_propria", via="heuristica",
                           confianca=0.98, needs_review=False)

    if _contem(norm, "pro labore", "pro-labore", "retirada titular",
               "distribuicao lucros", "salario socio"):
        return _montar("pessoal_prolabore", via="heuristica", confianca=0.95,
                       needs_review=True,
                       motivo="Retirada da empresa: definir se é pró-labore "
                              "ou distribuição de lucros.")

    if _contem(norm, "tarifa", "iof", "mdr", "taxa manutencao",
               "taxa extrato", "taxa liquidacao"):
        return _montar("taxas_tarifas", via="heuristica", confianca=0.95,
                       needs_review=False)

    if _contem(norm, "posto ", "combustivel", "gasolina", "ipiranga", "shell",
               "oficina", "claro", "vivo", "tim ", "internet",
               "mercado livre", "kalunga", "papelaria", "aluguel comercial"):
        prop = "gasto_pessoal" if ctx.tipo_conta == "pessoal" else "gasto_negocio"
        return _montar("custo_operacional", via="heuristica", confianca=0.90,
                       needs_review=False, proposito=prop)

    if _contem(norm, "venda balcao", "shopee", "kit festa"):
        return _montar("receita_venda", via="heuristica", confianca=0.90,
                       needs_review=False)

    if _contem(norm, "agencia dig ltda", "studio arte dig ltda", "consultoria",
               "servico prestado"):
        return _montar("receita_servico", via="heuristica", confianca=0.90,
                       needs_review=False)

    return None


def classificar_v2(descricao, valor, contexto):
    """Classificação determinística. Sem LLM, sem rede, sem estado."""
    norm = _norm(descricao)

    for pattern, cat in contexto.personal_rules.items():
        if cat in _DEFAULTS and _norm(pattern) in norm:
            return _montar(
                cat, via="regra_personalizada", confianca=0.98,
                needs_review=False,
                motivo=f"Regra personalizada: {pattern!r} -> {cat!r}",
            )

    resultado = _heuristica(norm, contexto)
    if resultado is not None:
        return resultado

    return _montar(
        "outros", via="heuristica", confianca=0.5,
        needs_review=True,
        motivo="Entrada sem evidência suficiente; requer confirmação.",
    )
