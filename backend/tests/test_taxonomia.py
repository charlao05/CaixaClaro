from dataclasses import FrozenInstanceError
from typing import get_args

from caixaclaro.domain.fiscal import taxonomia as tx


def test_taxonomia_version():
    assert tx.TAXONOMIA_VERSION == "v1"


def test_onze_categorias():
    assert len(tx.CATEGORIAS) == 11


def test_ids_batem_com_literal():
    """Todo id do Literal existe no dict, e vice-versa."""
    ids_literal = set(get_args(tx.CategoriaId))
    ids_dict = set(tx.CATEGORIAS.keys())
    assert ids_literal == ids_dict


def test_cada_categoria_tem_exatamente_uma_natureza():
    """Receita, despesa ou neutra — nunca duas, nunca nenhuma."""
    for cat in tx.CATEGORIAS.values():
        naturezas = [cat.receita, cat.despesa, cat.neutra]
        assert sum(naturezas) == 1, f"{cat.id}: receita={cat.receita} despesa={cat.despesa} neutra={cat.neutra}"


def test_receitas_sao_tres():
    receitas = sorted(c.id for c in tx.CATEGORIAS.values() if c.receita)
    assert receitas == ["receita_servico", "receita_venda", "salario"]


def test_despesas_sao_tres():
    despesas = sorted(c.id for c in tx.CATEGORIAS.values() if c.despesa)
    assert despesas == ["custo_operacional", "imposto_das", "taxas_tarifas"]


def test_neutras_sao_cinco():
    neutras = sorted(c.id for c in tx.CATEGORIAS.values() if c.neutra)
    assert neutras == [
        "emprestimo", "outros", "pessoal_prolabore",
        "reembolso", "transferencia_propria",
    ]


def test_salario_e_receita_mas_nao_despesa():
    """§4.1 marca salario como receita=sim (rendimento PF).
    M4 §9 exclui salario do faturamento empresarial — regra em outro módulo."""
    sal = tx.CATEGORIAS["salario"]
    assert sal.receita is True
    assert sal.despesa is False
    assert sal.neutra is False


def test_transferencia_propria_e_neutra():
    tp = tx.CATEGORIAS["transferencia_propria"]
    assert tp.receita is False
    assert tp.despesa is False
    assert tp.neutra is True


def test_categoria_valida():
    assert tx.categoria_valida("receita_servico")
    assert tx.categoria_valida("outros")
    assert not tx.categoria_valida("nao_existe")
    assert not tx.categoria_valida("")


def test_categoria_e_imutavel():
    cat = tx.CATEGORIAS["receita_servico"]
    try:
        cat.receita = False  # type: ignore
        assert False, "mutação deveria falhar (frozen=True)"
    except FrozenInstanceError:
        pass


def test_get_categoria_retorna_objeto():
    c = tx.get_categoria("imposto_das")
    assert c.id == "imposto_das"
    assert c.despesa is True
