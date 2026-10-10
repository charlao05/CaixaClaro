"""Vocabulário em linguagem simples — fonte única do que o usuário lê.

PRINCIPIOS §1 (backend como autoridade) e REGRA_ORIENTADOR §6 ("documentação
voltada ao usuário segue a mesma regra"): rótulos, opções de resposta e
formatação de moeda vivem aqui, não espalhados pelo React.

Nada aqui altera a taxonomia v1 (CONTRATOS_INTERNOS §4.1): os identificadores
persistidos continuam os mesmos; isto é só a tradução para gente.
"""
from decimal import Decimal


def brl(valor) -> str:
    """Formata em reais no padrão brasileiro, sempre sem sinal: R$ 1.234,56."""
    q = abs(Decimal(str(valor))).quantize(Decimal("0.01"))
    inteiro, _, centavos = f"{q:.2f}".partition(".")
    grupos: list[str] = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return "R$ " + ".".join(grupos) + "," + centavos


ROTULO_CATEGORIA: dict[str, str] = {
    "receita_servico": "Pagamento por trabalho ou serviço",
    "receita_venda": "Venda de produto",
    "salario": "Salário, aposentadoria ou benefício",
    "imposto_das": "Imposto ou guia",
    "taxas_tarifas": "Tarifa de banco ou maquininha",
    "custo_operacional": "Gasto do trabalho ou negócio",
    "transferencia_propria": "Dinheiro entre contas suas",
    "pessoal_prolabore": "Retirada do negócio para você",
    "reembolso": "Devolução ou reembolso",
    "emprestimo": "Empréstimo ou financiamento",
    "outros": "Falta você dizer o que foi",
}

# Propósitos que mudam o rótulo exibido sem mudar a categoria persistida.
ROTULO_PROPOSITO: dict[str, str] = {
    "gasto_pessoal": "Gasto pessoal ou da casa",
    "aporte_capital": "Dinheiro seu colocado no negócio",
    "dinheiro_terceiros": "Dinheiro de outra pessoa que passou pela conta",
    "rendimento_aplicacao": "Rendimento de aplicação",
    "doacao_heranca": "Presente, doação ou herança",
}


def rotulo(categoria: str | None, proposito: str | None = None) -> str:
    """Nome que o usuário vê para um lançamento."""
    if proposito in ROTULO_PROPOSITO:
        return ROTULO_PROPOSITO[proposito]
    return ROTULO_CATEGORIA.get(categoria or "outros", ROTULO_CATEGORIA["outros"])


# Opções de resposta da revisão. `categoria` é sempre um id da taxonomia v1;
# `proposito` refina sem inflar a taxonomia (mesmo padrão de M8-D3).
OPCOES_ENTRADA: tuple[dict, ...] = (
    {"id": "trabalho", "label": "Pagamento por um trabalho ou serviço",
     "descricao": "Alguém te pagou por algo que você fez.",
     "categoria": "receita_servico", "proposito": "trabalho_servico"},
    {"id": "venda", "label": "Venda de um produto",
     "descricao": "Você vendeu alguma coisa.",
     "categoria": "receita_venda", "proposito": "venda_produto"},
    {"id": "salario", "label": "Salário, aposentadoria ou benefício",
     "descricao": "Veio de um emprego com carteira ou do INSS.",
     "categoria": "salario", "proposito": "salario_aposentadoria"},
    {"id": "conta_propria", "label": "Dinheiro meu, vindo de outra conta minha",
     "descricao": "Só mudou de lugar. Não é renda.",
     "categoria": "transferencia_propria", "proposito": "transferencia_propria"},
    {"id": "devolucao", "label": "Alguém me devolveu um valor",
     "descricao": "Reembolso, estorno ou devolução de algo que eu paguei.",
     "categoria": "reembolso", "proposito": "devolucao_reembolso"},
    {"id": "emprestimo", "label": "Empréstimo que eu peguei",
     "descricao": "Dinheiro que vou ter que devolver. Não é renda.",
     "categoria": "emprestimo", "proposito": "emprestimo"},
    {"id": "doacao", "label": "Presente, ajuda da família ou doação",
     "descricao": "Recebi sem ter trabalhado ou vendido nada por isso.",
     "categoria": "outros", "proposito": "doacao_heranca"},
    {"id": "rendimento", "label": "Rendimento de aplicação",
     "descricao": "Juros de poupança, CDB ou outro investimento.",
     "categoria": "outros", "proposito": "rendimento_aplicacao"},
    {"id": "terceiros", "label": "Dinheiro de outra pessoa, só passou por mim",
     "descricao": "Recebi para repassar. Não é meu.",
     "categoria": "outros", "proposito": "dinheiro_terceiros"},
)

OPCOES_SAIDA: tuple[dict, ...] = (
    {"id": "gasto_trabalho", "label": "Gasto do meu trabalho ou negócio",
     "descricao": "Paguei algo que preciso para trabalhar.",
     "categoria": "custo_operacional", "proposito": "gasto_negocio"},
    {"id": "gasto_pessoal", "label": "Gasto pessoal ou da casa",
     "descricao": "Mercado, aluguel de casa, lazer, contas da família.",
     "categoria": "pessoal_prolabore", "proposito": "gasto_pessoal"},
    {"id": "imposto", "label": "Imposto ou guia (DAS, DARF, INSS)",
     "descricao": "Paguei um tributo.",
     "categoria": "imposto_das", "proposito": "imposto_taxa"},
    {"id": "tarifa", "label": "Tarifa de banco ou de maquininha",
     "descricao": "Cobrança do banco ou da operadora do cartão.",
     "categoria": "taxas_tarifas", "proposito": "imposto_taxa"},
    {"id": "conta_propria", "label": "Mandei para outra conta minha",
     "descricao": "Só mudou de lugar. Não é gasto.",
     "categoria": "transferencia_propria", "proposito": "transferencia_propria"},
    {"id": "emprestimo", "label": "Parcela de empréstimo, ou emprestei a alguém",
     "descricao": "Pagamento de dívida ou dinheiro que vai voltar.",
     "categoria": "emprestimo", "proposito": "emprestimo"},
    {"id": "devolucao", "label": "Devolvi dinheiro a alguém",
     "descricao": "Reembolso ou estorno que eu fiz.",
     "categoria": "reembolso", "proposito": "devolucao_reembolso"},
)


def opcoes_para(valor) -> tuple[dict, ...]:
    """Opções coerentes com a direção do dinheiro. Zero é tratado como entrada."""
    return OPCOES_SAIDA if Decimal(str(valor)) < 0 else OPCOES_ENTRADA
