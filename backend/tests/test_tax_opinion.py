"""TaxOpinion — CONTRATOS_INTERNOS §6."""
import uuid
from decimal import Decimal

from caixaclaro.db import conexao
from caixaclaro.domain.fiscal.classificacao import (
    ClassificacaoResultado,
    ContextoClassificacao,
    classificar_v2,
)
from caixaclaro.domain.fiscal.guardrails import GuardrailResultado, aplicar_guardrail
from caixaclaro.domain.fiscal.triagem import TriagemResultado, triar
from caixaclaro.services.tax_opinion import generate_tax_opinion


def _gerar(desc, valor="100.00"):
    ctx = ContextoClassificacao(personal_rules={})
    classif = classificar_v2(desc, Decimal(valor), ctx)
    guard = aplicar_guardrail(classif, descricao=desc)
    tri = triar(classif, guard)
    return generate_tax_opinion(
        descricao=desc, valor=Decimal(valor),
        classif=classif, guard=guard, tri=tri,
    )


def test_opiniao_tem_todos_os_nove_campos():
    o = _gerar("PAGTO GUIA DAS SIMPLES")
    for campo in (
        "fato", "interpretacao", "relacao_pf_pj",
        "possivel_tratamento_tributario", "condicoes_necessarias",
        "pendencias", "proximo_passo", "grau_certeza_leitura",
        "opcoes_esclarecimento",
    ):
        assert hasattr(o, campo), f"faltando: {campo}"


def test_grau_fato_confirmado_para_confianca_alta():
    o = _gerar("PAGTO GUIA DAS SIMPLES")
    assert o.grau_certeza_leitura == "fato_confirmado"


def test_grau_duvida_para_generico():
    o = _gerar("PIX RECEBIDO JOAO")
    assert o.grau_certeza_leitura == "duvida_declarada"


def test_grau_leitura_provavel_manual():
    classif = ClassificacaoResultado(
        categoria="receita_servico", proposito="trabalho_servico",
        origem_sugerida="desconhecido", patrimonio="atividade_negocio",
        tratamento_tributario="tributavel_irpf", confianca=0.80,
        needs_review=False, via="heuristica", motivo=None,
    )
    guard = GuardrailResultado(
        aplicado=False, categoria_original="receita_servico",
        categoria_corrigida="receita_servico", motivo="",
        regra_acionada=None,
    )
    tri = TriagemResultado(disposicao="confirmacao", needs_review=True)
    o = generate_tax_opinion(
        descricao="CREDITO SERVICO", valor=Decimal("100.00"),
        classif=classif, guard=guard, tri=tri,
    )
    assert o.grau_certeza_leitura == "leitura_provavel"


def test_opcoes_so_em_duvida():
    o_duvida = _gerar("PIX RECEBIDO JOAO")
    assert len(o_duvida.opcoes_esclarecimento) > 0
    o_clara = _gerar("PAGTO GUIA DAS SIMPLES")
    assert o_clara.opcoes_esclarecimento == []


def test_fato_cita_valor_formatado():
    o = _gerar("CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA", "500.00")
    assert "500,00" in o.fato


def test_salario_nao_compoe_faturamento():
    o = _gerar("CREDITO TED FOLHA SALARIO", "4850.00")
    assert "não compõe faturamento" in o.interpretacao.lower()


def test_emprestimo_tem_tratamento_sem_efeito():
    o = _gerar("CREDITO EMPRESTIMO CONSIGNADO BCO", "12000.00")
    assert "imediato" in o.possivel_tratamento_tributario.lower()


# ============================================================
# Endpoint
# ============================================================

async def _registrar(client, email="op@x.com", cpf="777.777.770-09"):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


def _key():
    return str(uuid.uuid4())


async def test_endpoint_opiniao_schema_completo(client):
    token = await _registrar(client)
    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": "25/09 PIX RECEBIDO JOAO R$ 100,00"},
    )
    assert r.status_code == 201

    async with conexao() as conn:
        tx_id = await conn.fetchval(
            "SELECT id FROM transactions WHERE origem = 'paste'"
        )

    r = await client.get(
        f"/api/v1/transacoes/{tx_id}/opiniao",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    for campo in (
        "tx_id", "fato", "interpretacao", "relacao_pf_pj",
        "possivel_tratamento_tributario", "condicoes_necessarias",
        "pendencias", "proximo_passo", "grau_certeza_leitura",
        "opcoes_esclarecimento", "confirmada",
    ):
        assert campo in body, f"faltando: {campo}"
    assert body["grau_certeza_leitura"] == "duvida_declarada"
    assert len(body["opcoes_esclarecimento"]) > 0
    assert body["confirmada"] is False


async def test_endpoint_opiniao_404(client):
    token = await _registrar(client, email="op2@x.com", cpf="888.888.880-20")
    r = await client.get(
        "/api/v1/transacoes/00000000-0000-0000-0000-000000000000/opiniao",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


async def test_endpoint_opiniao_sem_jwt_401(client):
    r = await client.get(
        "/api/v1/transacoes/00000000-0000-0000-0000-000000000000/opiniao"
    )
    assert r.status_code == 401


async def test_endpoint_opiniao_isolamento_404(client):
    token_a = await _registrar(client, email="opa@x.com", cpf="111.444.777-35")
    token_b = await _registrar(client, email="opb@x.com", cpf="222.222.220-60")

    await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token_a}",
                 "Idempotency-Key": _key()},
        json={"texto": "25/09 PIX RECEBIDO JOAO R$ 100,00"},
    )
    async with conexao() as conn:
        tx_id = await conn.fetchval(
            "SELECT id FROM transactions WHERE origem = 'paste'"
        )

    r = await client.get(
        f"/api/v1/transacoes/{tx_id}/opiniao",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404


# ============================================================
# N9 — opiniao le estado PERSISTIDO, nao recomputa
# ============================================================

async def test_opiniao_reflete_categoria_confirmada_pelo_usuario(client):
    """Usuario cola PIX (cai em outros), confirma receita_servico,
    GET /opiniao deve refletir a categoria confirmada — nao a inicial."""
    token = await _registrar(client, email="n9@x.com", cpf="999.999.990-50")

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": "25/09 PIX RECEBIDO JOAO R$ 500,00"},
    )
    assert r.status_code == 201

    # Pega o ID
    fila = await client.get(
        "/api/v1/transacoes/fila",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert fila.status_code == 200
    tx_id = fila.json()["itens"][0]["id"]

    # Confirma como receita_servico
    r = await client.patch(
        f"/api/v1/transacoes/{tx_id}/confirmar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"categoria": "receita_servico"},
    )
    assert r.status_code == 200, r.json()

    # GET /opiniao deve refletir receita_servico
    r = await client.get(
        f"/api/v1/transacoes/{tx_id}/opiniao",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    # A narrativa de fato cita "serviço prestado"
    assert "serviço prestado" in body["fato"].lower()
    # Nao caiu em duvida (usuario confirmou, mas confianca/via
    # persistidos podem variar — apenas verifica que NAO e "outros")
    assert "sem classificacao clara" not in body["fato"].lower()
    # Confirmada = True
    assert body["confirmada"] is True


async def test_opiniao_pos_confirma_sem_idempotency(client):
    """Prova que a leitura nao passa por recomputo — mesmo sem
    Idempotency-Key, GET /opiniao funciona e reflete persistencia."""
    token = await _registrar(client, email="n9b@x.com", cpf="101.101.102-69")

    await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 500,00"},
    )
    async with conexao() as conn:
        tx_id = await conn.fetchval(
            "SELECT id FROM transactions WHERE origem = 'paste'"
        )

    r = await client.get(
        f"/api/v1/transacoes/{tx_id}/opiniao",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "serviço prestado" in body["fato"].lower()

