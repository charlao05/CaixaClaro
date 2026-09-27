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
    "receita_servico": "Entrada de R$ {valor} referente a servico prestado.",
    "receita_venda": "Entrada de R$ {valor} referente a venda de produto.",
    "salario": "Entrada de R$ {valor} referente a salario ou provento.",
    "imposto_das": "Saida de R$ {valor} para pagamento de tributo.",
    "taxas_tarifas": "Saida de R$ {valor} referente a tarifa bancaria ou imposto sobre operacao.",
    "custo_operacional": "Saida de R$ {valor} referente a despesa da atividade.",
    "transferencia_propria": "Movimentacao de R$ {valor} entre contas proprias.",
    "pessoal_prolabore": "Saida de R$ {valor} referente a retirada do titular (ponte PF-PJ).",
    "reembolso": "Entrada de R$ {valor} referente a devolucao ou reembolso.",
    "emprestimo": "Movimentacao de R$ {valor} referente a emprestimo ou financiamento.",
    "outros": "Movimentacao de R$ {valor} sem classificacao clara.",
}

_INTERP = {
    "receita_servico": "Compoe faturamento MEI do ano. Sujeito ao teto anual.",
    "receita_venda": "Compoe faturamento MEI do ano. Sujeito ao teto anual.",
    "salario": "Renda pessoal. Nao compoe faturamento MEI.",
    "imposto_das": "Despesa tributaria. Nao compoe faturamento.",
    "taxas_tarifas": "Custo financeiro. Nao compoe faturamento.",
    "custo_operacional": "Custo da atividade. Reduz base, nao compoe faturamento.",
    "transferencia_propria": "Movimentacao neutra. Nao altera renda nem faturamento.",
    "pessoal_prolabore": "Retirada do titular. Nao e receita da empresa.",
    "reembolso": "Devolucao de valor. Nao compoe faturamento.",
    "emprestimo": "Recurso temporario. Nao compoe renda nem faturamento.",
    "outros": "Sem interpretacao fiscal ate confirmacao.",
}

_TRATAMENTO = {
    "receita_servico": "Informar no faturamento MEI.",
    "receita_venda": "Informar no faturamento MEI.",
    "salario": "Declarar como rendimento tributavel no IRPF.",
    "imposto_das": "Despesa dentro do regime MEI.",
    "taxas_tarifas": "Despesa operacional.",
    "custo_operacional": "Despesa operacional dedutivel.",
    "transferencia_propria": "Sem efeito fiscal.",
    "pessoal_prolabore": "Retirada de socio nao tributavel em PF.",
    "reembolso": "Sem efeito fiscal.",
    "emprestimo": "Sem efeito fiscal imediato.",
    "outros": "Indeterminado ate confirmacao.",
}

_PF_PJ = {
    "receita_servico": "Prestacao de servico a terceiro (empresarial).",
    "receita_venda": "Venda a terceiro (empresarial).",
    "salario": "Renda de pessoa fisica.",
    "imposto_das": "Obrigacao da atividade empresarial.",
    "taxas_tarifas": "Custo do negocio.",
    "custo_operacional": "Custo do negocio.",
    "transferencia_propria": "Circulacao entre contas do mesmo titular.",
    "pessoal_prolabore": "Retirada da empresa para PF do titular.",
    "reembolso": "Devolucao a PF ou PJ.",
    "emprestimo": "Obrigacao entre entidades.",
    "outros": "Relacao PF-PJ indeterminada.",
}

_CONDICAO = {
    "receita_servico": "Desde que o servico tenha sido efetivamente prestado.",
    "receita_venda": "Desde que a venda tenha sido efetivada.",
    "salario": "Desde que o vinculo ou beneficio esteja vigente.",
    "imposto_das": "Desde que o tributo seja devido pela atividade.",
    "taxas_tarifas": "Aplicavel a operacao bancaria efetivada.",
    "custo_operacional": "Desde que o gasto seja necessario a atividade.",
    "transferencia_propria": "Nenhuma condicao adicional.",
    "pessoal_prolabore": "Desde que o titular seja socio da PJ.",
    "reembolso": "Nenhuma condicao adicional.",
    "emprestimo": "Desde que o emprestimo esteja documentado.",
    "outros": "Depende de esclarecimento.",
}


def _opcoes_para(categoria: str) -> list[OpcaoEsclarecimento]:
    if categoria != "outros":
        return []
    return [
        OpcaoEsclarecimento(
            label="Trabalho ou servico",
            proposito="trabalho_servico",
            descricao="A entrada veio de servico prestado a terceiro.",
        ),
        OpcaoEsclarecimento(
            label="Venda de produto",
            proposito="venda_produto",
            descricao="A entrada veio de venda de produto.",
        ),
        OpcaoEsclarecimento(
            label="Transferencia entre contas proprias",
            proposito="transferencia_propria",
            descricao="A entrada veio de outra conta do proprio titular.",
        ),
        OpcaoEsclarecimento(
            label="Reembolso ou devolucao",
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
) -> TaxOpinion:
    """Gera TaxOpinion a partir do pipeline fiscal. Deterministico."""
    categoria = guard.categoria_corrigida
    valor_str = f"{valor:.2f}".replace(".", ",")

    fato = _FATO.get(categoria, _FATO["outros"]).format(valor=valor_str)
    interpretacao = _INTERP.get(categoria, _INTERP["outros"])
    relacao = _PF_PJ.get(categoria, _PF_PJ["outros"])
    tratamento = _TRATAMENTO.get(categoria, _TRATAMENTO["outros"])
    condicao = _CONDICAO.get(categoria, _CONDICAO["outros"])

    if guard.aplicado:
        condicao = (
            f"Guardrail §6 aplicado ({guard.regra_acionada}): "
            f"categoria original era {guard.categoria_original}. "
            + condicao
        )

    if tri.needs_review:
        pendencias = "Classificacao automatica aguarda confirmacao."
        proximo = "Revisar na fila e confirmar ou corrigir."
    else:
        pendencias = "Nenhuma pendencia identificada."
        proximo = "Nenhuma acao necessaria."

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
