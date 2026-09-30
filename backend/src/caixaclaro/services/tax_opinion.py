"""TaxOpinion — CONTRATOS_INTERNOS §6."""
from dataclasses import dataclass, field
from decimal import Decimal

from ..domain.fiscal.classificacao import ClassificacaoResultado
from ..domain.fiscal.guardrails import GuardrailResultado
from ..domain.fiscal.triagem import TriagemResultado

GrauCerteza = str


@dataclass(frozen=True)
class OpcaoEsclarecimento:
    label: str
    proposito: str
    descricao: str


@dataclass(frozen=True)
class TaxOpinion:
    fato: str
    interpretacao: str
    relacao_pf_pj: str
    possivel_tratamento_tributario: str
    condicoes_necessarias: str
    pendencias: str
    proximo_passo: str
    grau_certeza_leitura: GrauCerteza
    opcoes_esclarecimento: list[OpcaoEsclarecimento] = field(default_factory=list)


def _grau(confianca: float, via: str) -> GrauCerteza:
    if via == "fallback" or confianca < 0.70:
        return "duvida_declarada"
    if confianca >= 0.90:
        return "fato_confirmado"
    return "leitura_provavel"


_FATO = {
    "receita_servico": "Entrada de R$ {valor} referente a serviço prestado.",
    "receita_venda": "Entrada de R$ {valor} referente a venda de produto.",
    "salario": "Entrada de R$ {valor} referente a salário ou provento.",
    "imposto_das": "Saída de R$ {valor} para pagamento de tributo.",
    "taxas_tarifas": "Saída de R$ {valor} referente a tarifa bancária ou imposto sobre operação.",
    "custo_operacional": "Saída de R$ {valor} referente a despesa da atividade.",
    "transferencia_propria": "Movimentação de R$ {valor} entre contas próprias.",
    "pessoal_prolabore": "Saída de R$ {valor} referente a retirada do titular (ponte PF-PJ).",
    "reembolso": "Entrada de R$ {valor} referente a devolução ou reembolso.",
    "emprestimo": "Movimentação de R$ {valor} referente a empréstimo ou financiamento.",
    "outros": "Movimentação de R$ {valor} sem classificação clara.",
}

_INTERP = {
    "receita_servico": "Compõe faturamento MEI do ano. Sujeito ao teto anual.",
    "receita_venda": "Compõe faturamento MEI do ano. Sujeito ao teto anual.",
    "salario": "Renda pessoal. Não compõe faturamento MEI.",
    "imposto_das": "Despesa tributária. Não compõe faturamento.",
    "taxas_tarifas": "Custo financeiro. Não compõe faturamento.",
    "custo_operacional": "Custo da atividade. Reduz base, não compõe faturamento.",
    "transferencia_propria": "Movimentação neutra. Não altera renda nem faturamento.",
    "pessoal_prolabore": "Retirada do titular. Não é receita da empresa.",
    "reembolso": "Devolução de valor. Não compõe faturamento.",
    "emprestimo": "Recurso temporário. Não compõe renda nem faturamento.",
    "outros": "Sem interpretação fiscal até confirmação.",
}

_TRATAMENTO = {
    "receita_servico": "Informar no faturamento MEI.",
    "receita_venda": "Informar no faturamento MEI.",
    "salario": "Declarar como rendimento tributável no IRPF.",
    "imposto_das": "Despesa dentro do regime MEI.",
    "taxas_tarifas": "Despesa operacional.",
    "custo_operacional": "Despesa operacional dedutível.",
    "transferencia_propria": "Sem efeito fiscal.",
    "pessoal_prolabore": "Retirada de sócio não tributável em PF.",
    "reembolso": "Sem efeito fiscal.",
    "emprestimo": "Sem efeito fiscal imediato.",
    "outros": "Indeterminado até confirmação.",
}

_PF_PJ = {
    "receita_servico": "Prestação de serviço a terceiro (empresarial).",
    "receita_venda": "Venda a terceiro (empresarial).",
    "salario": "Renda de pessoa física.",
    "imposto_das": "Obrigação da atividade empresarial.",
    "taxas_tarifas": "Custo do negócio.",
    "custo_operacional": "Custo do negócio.",
    "transferencia_propria": "Circulação entre contas do mesmo titular.",
    "pessoal_prolabore": "Retirada da empresa para PF do titular.",
    "reembolso": "Devolução a PF ou PJ.",
    "emprestimo": "Obrigação entre entidades.",
    "outros": "Relação PF-PJ indeterminada.",
}

_CONDICAO = {
    "receita_servico": "Desde que o serviço tenha sido efetivamente prestado.",
    "receita_venda": "Desde que a venda tenha sido efetivada.",
    "salario": "Desde que o vínculo ou benefício esteja vigente.",
    "imposto_das": "Desde que o tributo seja devido pela atividade.",
    "taxas_tarifas": "Aplicável à operação bancária efetivada.",
    "custo_operacional": "Desde que o gasto seja necessário à atividade.",
    "transferencia_propria": "Nenhuma condição adicional.",
    "pessoal_prolabore": "Desde que o titular seja sócio da PJ.",
    "reembolso": "Nenhuma condição adicional.",
    "emprestimo": "Desde que o empréstimo esteja documentado.",
    "outros": "Depende de esclarecimento.",
}


def _opcoes_para(categoria: str) -> list[OpcaoEsclarecimento]:
    if categoria != "outros":
        return []
    return [
        OpcaoEsclarecimento(
            label="Trabalho ou serviço",
            proposito="trabalho_servico",
            descricao="A entrada veio de serviço prestado a terceiro.",
        ),
        OpcaoEsclarecimento(
            label="Venda de produto",
            proposito="venda_produto",
            descricao="A entrada veio de venda de produto.",
        ),
        OpcaoEsclarecimento(
            label="Transferência entre contas próprias",
            proposito="transferencia_propria",
            descricao="A entrada veio de outra conta do próprio titular.",
        ),
        OpcaoEsclarecimento(
            label="Reembolso ou devolução",
            proposito="devolucao_reembolso",
            descricao="A entrada devolve valor antes pago.",
        ),
    ]


def generate_tax_opinion(
    *,
    descricao: str,
    valor: Decimal,
    classif: ClassificacaoResultado,
    guard: GuardrailResultado,
    tri: TriagemResultado,
    regime: str = "MEI",
) -> TaxOpinion:
    """Gera TaxOpinion a partir do pipeline fiscal. Deterministico."""
    categoria = guard.categoria_corrigida
    valor_str = f"{valor:.2f}".replace(".", ",")

    fato = _FATO.get(categoria, _FATO["outros"]).format(valor=valor_str)
    interpretacao = _INTERP.get(categoria, _INTERP["outros"])
    relacao = _PF_PJ.get(categoria, _PF_PJ["outros"])
    tratamento = _TRATAMENTO.get(categoria, _TRATAMENTO["outros"])
    condicao = _CONDICAO.get(categoria, _CONDICAO["outros"])

    # D5: somente categorias com diferenca material definida no
    # contrato recebem variante por regime. O restante permanece
    # deterministico pelo comportamento existente.
    if regime == "PF":
        if categoria == "receita_servico":
            interpretacao = (
                "Rendimento de pessoa fisica decorrente de trabalho "
                "nao assalariado. Pode estar sujeito ao carnê-leao."
            )
            tratamento = (
                "Avaliar recolhimento mensal de IRPF pelo carnê-leao "
                "e declaracao anual, conforme a natureza do rendimento."
            )
        elif categoria == "receita_venda":
            interpretacao = (
                "Venda realizada por pessoa fisica. O tratamento depende "
                "de ser alienacao de bem ou atividade habitual de revenda."
            )
            tratamento = (
                "Avaliar o tratamento de ganho de capital ou de atividade "
                "habitual, conforme a natureza da venda."
            )
        elif categoria == "custo_operacional":
            interpretacao = (
                "Custo relacionado a atividade de pessoa fisica. "
                "Pode ser dedutivel no Livro Caixa quando permitido."
            )
            tratamento = (
                "Pode ser deduzido no Livro Caixa quando necessario "
                "a atividade, permitido pela legislacao e devidamente comprovado."
            )

    if guard.aplicado:
        condicao = (
            f"Guardrail §6 aplicado ({guard.regra_acionada}): "
            f"categoria original era {guard.categoria_original}. "
            + condicao
        )

    if tri.needs_review:
        pendencias = "Classificação automática aguarda confirmação."
        proximo = "Revisar e confirmar ou corrigir."
    else:
        pendencias = "Nenhuma pendência identificada."
        proximo = "Nenhuma ação necessária."

    grau = _grau(classif.confianca, classif.via)
    opcoes = _opcoes_para(categoria)

    return TaxOpinion(
        fato=fato,
        interpretacao=interpretacao,
        relacao_pf_pj=relacao,
        possivel_tratamento_tributario=tratamento,
        condicoes_necessarias=condicao,
        pendencias=pendencias,
        proximo_passo=proximo,
        grau_certeza_leitura=grau,
        opcoes_esclarecimento=opcoes,
    )
