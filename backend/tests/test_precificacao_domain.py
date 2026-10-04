"""Testes puros de domain/negocio/precificacao.py — sem banco.

Cobre os quatro itens da Categoria I (docs/CONSULTA_CRC_ES.md) e a
conformidade com docs/REGRA_ORIENTADOR.md: toda saída rotulada por
estado, recusa explícita quando faltam dados, nenhum default
silencioso.
"""

import pytest

from caixaclaro.domain.negocio.precificacao import (
    DadosInsuficientes,
    calcular_cenario,
)


def test_item1_diferenca_preco_custo():
    c = calcular_cenario(nome="A", preco="50", custo_variavel_unitario="18")
    diff = next(x for x in c.calculos if x.nome == "diferenca_preco_custo")
    assert diff.resultado == "32"
    assert diff.estado == "calculo"
    assert diff.formula == "preco - custo_variavel_unitario"


def test_item2_margem_contribuicao_reais_e_percentual():
    c = calcular_cenario(nome="A", preco="50", custo_variavel_unitario="20")
    reais = next(x for x in c.calculos if x.nome == "margem_contribuicao_unitaria_reais")
    pct = next(x for x in c.calculos if x.nome == "margem_contribuicao_unitaria_percentual")
    assert reais.resultado == "30"
    assert pct.resultado == "60.00"  # 30/50 * 100
    assert pct.estado == "calculo"


def test_item2_margem_percentual_com_preco_zero_vira_limitacao():
    """REGRA_ORIENTADOR §3: recusar calcular, nunca dividir por zero silenciosamente."""
    c = calcular_cenario(nome="A", preco="0", custo_variavel_unitario="10")
    pct = next(x for x in c.calculos if x.nome == "margem_contribuicao_unitaria_percentual")
    assert pct.estado == "limitacao"
    assert pct.resultado is None
    assert pct.limitacao is not None
    assert any("zero" in lim.lower() for lim in c.limitacoes)


def test_item3_ponto_equilibrio_unidades_e_receita():
    c = calcular_cenario(
        nome="A", preco="50", custo_variavel_unitario="30",
        custos_fixos_periodo="2000",
    )
    un = next(x for x in c.calculos if x.nome == "ponto_equilibrio_unidades")
    rc = next(x for x in c.calculos if x.nome == "ponto_equilibrio_receita")
    # margem = 20; PE unidades = 2000/20 = 100; PE receita = 100*50 = 5000
    assert un.resultado == "100.00"
    assert rc.resultado == "5000.00"
    assert un.estado == "calculo"
    assert rc.estado == "calculo"


def test_item3_sem_custos_fixos_vira_limitacao_nao_erro():
    """O sistema se recusa a calcular PE, mas não derruba o cenário inteiro."""
    c = calcular_cenario(nome="A", preco="50", custo_variavel_unitario="30")
    un = next(x for x in c.calculos if x.nome == "ponto_equilibrio_unidades")
    assert un.estado == "limitacao"
    assert un.resultado is None
    # diferenca_preco_custo e margem continuam calculados normalmente
    diff = next(x for x in c.calculos if x.nome == "diferenca_preco_custo")
    assert diff.estado == "calculo"


def test_item3_margem_nao_positiva_ponto_equilibrio_indeterminado():
    """Preço não cobre custo: PE matematicamente indeterminado -> LIMITACAO."""
    c = calcular_cenario(
        nome="A", preco="10", custo_variavel_unitario="15",
        custos_fixos_periodo="1000",
    )
    un = next(x for x in c.calculos if x.nome == "ponto_equilibrio_unidades")
    assert un.estado == "limitacao"
    assert "não é positiva" in un.limitacao or "nao e positiva" in (un.limitacao or "").lower()


def test_recusa_calcular_sem_preco():
    """As cinco perguntas de aceite: pode se recusar e dizer 'faltam dados'."""
    with pytest.raises(DadosInsuficientes) as exc:
        calcular_cenario(nome="A", preco=None, custo_variavel_unitario="10")
    assert exc.value.campo == "preco"


def test_recusa_calcular_custo_negativo():
    with pytest.raises(DadosInsuficientes):
        calcular_cenario(nome="A", preco="10", custo_variavel_unitario="-5")


def test_recusa_calcular_valor_nao_numerico():
    with pytest.raises(DadosInsuficientes):
        calcular_cenario(nome="A", preco="abc", custo_variavel_unitario="10")


def test_volume_hipotese_registrado_mas_nao_vira_receita_projetada():
    """Decisão deliberada: volume vira HIPOTESE registrada, não cálculo de receita."""
    c = calcular_cenario(
        nome="A", preco="50", custo_variavel_unitario="30", volume_hipotese="100",
    )
    assert c.hipoteses["volume_hipotese"] == "100"
    nomes_calculados = {x.nome for x in c.calculos}
    assert "receita_projetada" not in nomes_calculados
    assert "lucro_projetado" not in nomes_calculados
    assert any("não foi usado para projetar receita" in lim for lim in c.limitacoes)


def test_toda_saida_tem_estado_explicito():
    """REGRA_ORIENTADOR §2, pergunta 2: toda saída rotulada por estado."""
    c = calcular_cenario(
        nome="A", preco="50", custo_variavel_unitario="30",
        custos_fixos_periodo="2000", volume_hipotese="10",
    )
    for calc in c.calculos:
        assert calc.estado in ("calculo", "limitacao")
        if calc.estado == "calculo":
            assert calc.resultado is not None
        if calc.estado == "limitacao":
            assert calc.resultado is None
            assert calc.limitacao is not None


def test_limitacao_generica_sempre_presente():
    """REGRA_ORIENTADOR §2, pergunta 3: limitação visível na própria saída,
    não só em rodapé — aqui, sempre no campo limitacoes do cenário."""
    c = calcular_cenario(nome="A", preco="50", custo_variavel_unitario="30")
    assert any("não é uma conclusão sobre lucro" in lim.lower()
               or "nao e uma conclusao sobre lucro" in lim.lower()
               for lim in c.limitacoes)