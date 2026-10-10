"""TaxOpinion — CONTRATOS_INTERNOS §6, escrita sob docs/REGRA_ORIENTADOR.md.

O que mudou em 2026-10-09 (ver docs/AUDITORIA_JORNADA_2026-10-09.md):

  - Texto em linguagem de quem está começando, sem vocabulário interno
    (nada de "guardrail", "ponte PF-PJ", "§6").
  - Cada frase respeita os estados da REGRA_ORIENTADOR: o que o usuário
    informou é dito como informado; o que veio de palavra-chave é dito
    como leitura; o que depende de dado que o CaixaClaro não tem é dito
    como limitação. Nenhuma frase manda declarar, deduzir ou concluir.
  - `fato_confirmado` só existe quando o USUÁRIO confirmou
    (M4_CONTRATO §16: "classificação automática ≠ confirmação").
  - O texto acompanha o perfil (MEI / Simples / pessoa física) e a direção
    do dinheiro (entrou / saiu), que é fato do extrato.

Determinístico: sem LLM, sem rede.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from ..domain.fiscal.classificacao import ClassificacaoResultado
from ..domain.fiscal.guardrails import GuardrailResultado
from ..domain.fiscal.triagem import TriagemResultado
from .rotulos import brl, opcoes_para

GrauCerteza = str


@dataclass(frozen=True)
class OpcaoEsclarecimento:
    label: str
    proposito: str
    descricao: str
    categoria: str = "outros"


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


def _grau(confianca: float, via: str, confirmada: bool = False) -> GrauCerteza:
    if confirmada:
        return "fato_confirmado"
    if via == "fallback" or confianca < 0.70:
        return "duvida_declarada"
    return "leitura_provavel"


# O que é, em uma expressão que cabe depois de "foi" / "parece ser".
_O_QUE = {
    "receita_servico": "pagamento por um trabalho ou serviço",
    "receita_venda": "venda de produto",
    "salario": "salário, aposentadoria ou benefício",
    "imposto_das": "pagamento de imposto ou guia",
    "taxas_tarifas": "tarifa de banco ou de maquininha",
    "custo_operacional": "gasto do seu trabalho ou negócio",
    "transferencia_propria": "dinheiro passando entre contas suas",
    "pessoal_prolabore": "retirada do negócio para você",
    "reembolso": "devolução ou reembolso",
    "emprestimo": "empréstimo ou financiamento",
}

_O_QUE_PROPOSITO = {
    "gasto_pessoal": "gasto pessoal ou da casa",
    "aporte_capital": "dinheiro seu colocado no negócio",
    "dinheiro_terceiros": "dinheiro de outra pessoa que só passou pela sua conta",
    "rendimento_aplicacao": "rendimento de aplicação financeira",
    "doacao_heranca": "presente, doação ou herança",
}

_SIGNIFICA = {
    "salario": "É renda pessoal. Não compõe faturamento de negócio.",
    "imposto_das": "É pagamento de imposto. Não compõe faturamento.",
    "taxas_tarifas": "É custo de banco ou de maquininha. Não compõe faturamento.",
    "transferencia_propria": "O dinheiro só mudou de lugar. Não é renda nem gasto.",
    "pessoal_prolabore": (
        "É dinheiro do negócio indo para o seu uso pessoal. "
        "Não é gasto do negócio nem faturamento."
    ),
    "reembolso": "É um valor voltando. Não é renda nova nem faturamento.",
    "emprestimo": (
        "É dinheiro emprestado, que precisa ser devolvido. "
        "Não é renda nem faturamento."
    ),
    "outros": "Ainda não dá para dizer o que este lançamento significa.",
}

_SIGNIFICA_PROPOSITO = {
    "gasto_pessoal": "É gasto da sua vida pessoal. Não é gasto do trabalho.",
    "aporte_capital": (
        "É dinheiro seu entrando no negócio. Não é faturamento e, por si só, "
        "não é renda."
    ),
    "dinheiro_terceiros": (
        "Se o dinheiro é de outra pessoa e só passou pela sua conta, "
        "ele não é renda sua nem faturamento."
    ),
    "rendimento_aplicacao": (
        "É o que uma aplicação rendeu. É diferente do dinheiro que você "
        "aplicou ou resgatou."
    ),
    "doacao_heranca": "É um valor recebido sem trabalho ou venda em troca.",
}

_SIGNIFICA_RECEITA = {
    "MEI": "Entra na soma do seu faturamento como MEI neste ano.",
    "SIMPLES": "Entra na soma das receitas do seu negócio.",
    "PF": "É renda do seu trabalho por conta própria, recebida no seu CPF.",
}

# Pessoa física + "venda de produto": o CaixaClaro não sabe se vender é a
# atividade da pessoa ou se foi a venda de algo que era dela. O texto declara
# essa limitação em vez de afirmar "renda do seu trabalho" (REGRA_ORIENTADOR
# §4: não apresentar como conclusão o que depende de dado que o produto não
# tem). O main já fazia essa distinção; ela tinha se perdido no M13.
_SIGNIFICA_VENDA_PF = (
    "É dinheiro de uma venda, recebido no seu CPF. Vender com frequência, "
    "para ganhar dinheiro, é uma coisa; vender uma vez algo que era seu é "
    "outra. O CaixaClaro não sabe qual é o seu caso."
)
_PESSOAL_OU_TRABALHO_VENDA_PF = (
    "Depende: se vender é o seu trabalho, é do trabalho; se era um bem seu, "
    "é da vida pessoal."
)
_IMPOSTO_VENDA_PF = (
    "Depende do tipo de venda. Venda feita com frequência, como atividade, "
    "pode entrar no imposto de renda da pessoa. A venda eventual de um bem "
    "que era seu segue outra regra (ganho de capital), que depende do bem e "
    "do valor. O CaixaClaro não conclui qual das duas vale para você."
)

_SIGNIFICA_CUSTO = {
    "MEI": (
        "É um gasto para trabalhar. Ele não diminui o faturamento que conta "
        "para o limite do MEI."
    ),
    "SIMPLES": "É um gasto do negócio. Não é faturamento.",
    "PF": "É um gasto ligado ao seu trabalho.",
}

_PESSOAL_OU_TRABALHO = {
    "receita_servico": "Do trabalho.",
    "receita_venda": "Do trabalho.",
    "salario": "Da vida pessoal.",
    "imposto_das": (
        "Depende do imposto: a guia mensal do MEI (DAS) é do negócio; "
        "DARF e carnê-leão costumam ser da pessoa."
    ),
    "taxas_tarifas": "Depende de qual conta cobrou a tarifa.",
    "custo_operacional": "Do trabalho.",
    "transferencia_propria": "De nenhum dos dois: é o mesmo dono dos dois lados.",
    "pessoal_prolabore": "É a passagem do dinheiro do negócio para a pessoa.",
    "reembolso": "Depende do que foi devolvido.",
    "emprestimo": "Depende de quem pegou o empréstimo: você ou o negócio.",
    "outros": "Ainda não sabemos.",
}

_PESSOAL_OU_TRABALHO_PROPOSITO = {
    "gasto_pessoal": "Da vida pessoal.",
    "aporte_capital": "É a passagem do dinheiro da pessoa para o negócio.",
    "dinheiro_terceiros": "De nenhum dos dois, se o dinheiro for mesmo de outra pessoa.",
    "rendimento_aplicacao": "Depende de quem é o dono da aplicação: você ou o negócio.",
    "doacao_heranca": "Da vida pessoal.",
}

_IMPOSTO = {
    "salario": (
        "Salário e aposentadoria podem entrar no imposto de renda da pessoa. "
        "Os valores oficiais ficam no informe de rendimentos de quem paga."
    ),
    "imposto_das": (
        "Este lançamento já é um pagamento de imposto. "
        "O comprovante dele serve como registro."
    ),
    "taxas_tarifas": (
        "Tarifa, por si só, não é imposto a pagar. Se ela conta como gasto "
        "do trabalho depende do seu caso."
    ),
    "transferencia_propria": (
        "Passar dinheiro entre contas do mesmo dono, por si só, não gera imposto."
    ),
    "pessoal_prolabore": (
        "O que o dono retira do negócio pode ser isento ou tributável no "
        "imposto de renda da pessoa. Isso depende de quanto é lucro e de como "
        "ele é apurado — o CaixaClaro não consegue concluir só pelo extrato."
    ),
    "reembolso": (
        "Receber de volta um valor que já era seu, em geral, não é renda. "
        "Depende do que foi devolvido."
    ),
    "emprestimo": (
        "Pegar ou pagar um empréstimo, por si só, não é renda. "
        "Juros e financiamentos têm regras próprias."
    ),
    "outros": "Não dá para dizer antes de saber o que foi.",
}

_IMPOSTO_PROPOSITO = {
    "gasto_pessoal": (
        "Gasto pessoal não entra na conta do negócio. Alguns gastos pessoais "
        "têm regras próprias no imposto de renda da pessoa."
    ),
    "aporte_capital": (
        "Colocar dinheiro próprio no negócio (aporte de capital social), "
        "por si só, não costuma ser renda. O registro correto depende do "
        "tipo de empresa."
    ),
    "dinheiro_terceiros": (
        "Dinheiro que não é seu, em regra, não é renda sua. É preciso "
        "conseguir mostrar de quem ele era e para quem foi repassado."
    ),
    "rendimento_aplicacao": (
        "Rendimento de aplicação pode ser isento, já vir com imposto "
        "descontado ou seguir regra própria, conforme o tipo de aplicação. "
        "O informe de rendimentos do banco mostra o tratamento."
    ),
    "doacao_heranca": (
        "Em regra, doação e herança não pagam imposto de renda, mas existe "
        "um imposto estadual (ITCMD) que pode valer para elas. "
        "Depende do valor e do estado."
    ),
}

_IMPOSTO_RECEITA = {
    "MEI": (
        "O MEI paga um valor fixo por mês (a guia DAS), que não muda a cada "
        "venda. O que tem limite é a soma do ano. Nota fiscal e imposto de "
        "renda da pessoa dependem do seu caso."
    ),
    "SIMPLES": (
        "No Simples Nacional o imposto é calculado sobre a receita do mês, "
        "na apuração do negócio. O CaixaClaro não faz essa apuração."
    ),
    "PF": (
        "Renda de trabalho sem carteira pode entrar no imposto de renda da "
        "pessoa e, em alguns casos, no carnê-leão. Se isso vale para você "
        "depende de quanto e de quem você recebeu."
    ),
}

_IMPOSTO_CUSTO = {
    "MEI": (
        "A guia mensal do MEI (DAS) não diminui com gastos. Gastos do "
        "trabalho podem importar na hora de apurar o lucro para o imposto de "
        "renda da pessoa — isso depende de comprovantes e do seu caso."
    ),
    "SIMPLES": (
        "No Simples o imposto é sobre a receita; gastos não entram nessa "
        "conta, mas fazem parte do resultado do negócio."
    ),
    "PF": (
        "Para quem trabalha por conta própria no CPF, alguns gastos do "
        "trabalho podem entrar no livro-caixa, quando a lei permite e há "
        "comprovante. O CaixaClaro não decide isso."
    ),
}

_VALE_SE = {
    "receita_servico": "O trabalho foi feito por você e este valor é o pagamento dele.",
    "receita_venda": "Este valor é mesmo de uma venda sua.",
    "salario": "O valor veio de um empregador ou do INSS.",
    "imposto_das": "O pagamento é mesmo de um imposto ou guia.",
    "taxas_tarifas": "A cobrança é do banco ou da maquininha.",
    "custo_operacional": "O gasto foi para o seu trabalho, e não para uso pessoal.",
    "transferencia_propria": "As duas contas são suas.",
    "pessoal_prolabore": "O dinheiro saiu do que é do negócio para você.",
    "reembolso": "O valor corresponde a algo que foi pago antes.",
    "emprestimo": "Existe mesmo um empréstimo ou financiamento por trás deste valor.",
    "outros": "Depende do que você contar sobre este lançamento.",
}

_VALE_SE_PROPOSITO = {
    "gasto_pessoal": "O gasto não tem relação com o seu trabalho.",
    "aporte_capital": "O dinheiro era seu e foi colocado no negócio.",
    "dinheiro_terceiros": "O dinheiro é de outra pessoa e foi (ou será) repassado.",
    "rendimento_aplicacao": "O valor é o rendimento, e não o resgate do que foi aplicado.",
    "doacao_heranca": "Você não trabalhou nem vendeu nada em troca deste valor.",
}

# Regras de proteção aplicadas na ingestão, ditas em português comum.
_PROTECAO = {
    "emprestimo": "A descrição fala em empréstimo, então o valor não foi tratado como renda.",
    "estorno": "A descrição fala em devolução, então o valor não foi tratado como renda.",
    "ponte_pf_pj": (
        "Parece uma retirada do negócio para o dono, e isso sempre pede a "
        "sua confirmação."
    ),
    "cpf_proprio": (
        "O CPF de quem enviou é o seu, então foi tratado como dinheiro entre "
        "contas suas."
    ),
    "tributo": "A descrição indica imposto, então não foi tratado como gasto comum.",
}


def _regime(regime: str | None) -> str:
    return regime if regime in ("MEI", "SIMPLES", "PF") else "MEI"


def _escolher(categoria: str, proposito: str | None, por_proposito: dict, por_categoria: dict) -> str:
    if proposito in por_proposito:
        return por_proposito[proposito]
    return por_categoria.get(categoria, por_categoria["outros"])


def _opcoes(categoria: str, valor: Decimal, confirmada: bool) -> list[OpcaoEsclarecimento]:
    if categoria != "outros" or confirmada:
        return []
    return [
        OpcaoEsclarecimento(
            label=o["label"],
            proposito=o["proposito"],
            descricao=o["descricao"],
            categoria=o["categoria"],
        )
        for o in opcoes_para(valor)
    ]


def generate_tax_opinion(
    *,
    descricao: str,
    valor: Decimal,
    classif: ClassificacaoResultado,
    guard: GuardrailResultado,
    tri: TriagemResultado,
    regime: str = "MEI",
    confirmada: bool = False,
) -> TaxOpinion:
    """Gera a leitura de um lançamento a partir do pipeline fiscal."""
    categoria = guard.categoria_corrigida
    proposito = classif.proposito
    reg = _regime(regime)
    saiu = Decimal(str(valor)) < 0
    indefinido = categoria == "outros" and proposito not in _O_QUE_PROPOSITO

    # 1. O que aconteceu — a direção e o valor são FATO do extrato.
    direcao = "Saíram" if saiu else "Entraram"
    o_que = _O_QUE_PROPOSITO.get(proposito) or _O_QUE.get(categoria)
    if indefinido or o_que is None:
        leitura = "Só pela descrição do extrato não dá para saber o que foi."
    elif confirmada:
        leitura = f"Você informou que foi {o_que}."
    else:
        leitura = f"Pela descrição, parece ser {o_que}. Você ainda não confirmou."
    fato = f"{direcao} {brl(valor)}. {leitura}"

    venda_no_cpf = categoria == "receita_venda" and reg == "PF"

    # 2. O que isso significa
    if proposito in _SIGNIFICA_PROPOSITO:
        interpretacao = _SIGNIFICA_PROPOSITO[proposito]
    elif venda_no_cpf:
        interpretacao = _SIGNIFICA_VENDA_PF
    elif categoria in ("receita_servico", "receita_venda"):
        interpretacao = _SIGNIFICA_RECEITA[reg]
    elif categoria == "custo_operacional":
        interpretacao = _SIGNIFICA_CUSTO[reg]
    else:
        interpretacao = _SIGNIFICA.get(categoria, _SIGNIFICA["outros"])

    # 3. É da vida pessoal ou do trabalho?
    relacao = _escolher(
        categoria, proposito, _PESSOAL_OU_TRABALHO_PROPOSITO, _PESSOAL_OU_TRABALHO
    )
    if venda_no_cpf and proposito not in _PESSOAL_OU_TRABALHO_PROPOSITO:
        relacao = _PESSOAL_OU_TRABALHO_VENDA_PF

    # 4. Tem a ver com imposto?
    if proposito in _IMPOSTO_PROPOSITO:
        tratamento = _IMPOSTO_PROPOSITO[proposito]
    elif venda_no_cpf:
        tratamento = _IMPOSTO_VENDA_PF
    elif categoria in ("receita_servico", "receita_venda"):
        tratamento = _IMPOSTO_RECEITA[reg]
    elif categoria == "custo_operacional":
        tratamento = _IMPOSTO_CUSTO[reg]
    else:
        tratamento = _IMPOSTO.get(categoria, _IMPOSTO["outros"])

    # 5. Isso vale se...
    condicao = _escolher(categoria, proposito, _VALE_SE_PROPOSITO, _VALE_SE)

    # 6. O que o CaixaClaro não sabe
    if confirmada:
        pendencias = (
            "O CaixaClaro registrou o que você informou. Ele não confere "
            "nota fiscal, contrato nem comprovante."
        )
    elif tri.needs_review:
        pendencias = "Falta você dizer o que foi este lançamento."
    else:
        pendencias = (
            "Esta leitura veio só da descrição do extrato. "
            "Ela não foi confirmada por você."
        )
    if guard.aplicado and guard.regra_acionada in _PROTECAO:
        pendencias = f"{_PROTECAO[guard.regra_acionada]} {pendencias}"

    # 7. O que dá para fazer agora
    if confirmada:
        proximo = "Nada pendente no CaixaClaro para este lançamento."
    elif tri.needs_review:
        proximo = "Responder o que foi este lançamento."
    else:
        proximo = "Se a leitura estiver errada, você pode corrigir."

    return TaxOpinion(
        fato=fato,
        interpretacao=interpretacao,
        relacao_pf_pj=relacao,
        possivel_tratamento_tributario=tratamento,
        condicoes_necessarias=condicao,
        pendencias=pendencias,
        proximo_passo=proximo,
        grau_certeza_leitura=_grau(classif.confianca, classif.via, confirmada),
        opcoes_esclarecimento=_opcoes(categoria, Decimal(str(valor)), confirmada),
    )
