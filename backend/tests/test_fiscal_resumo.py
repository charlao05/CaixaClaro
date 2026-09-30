"""Resumo fiscal — leitura de fiscal_state + alerts."""
import json
import uuid
from decimal import Decimal

from caixaclaro.db import conexao


async def _registrar(client, email="fr@x.com", cpf="333.333.330-90"):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


def _key():
    return str(uuid.uuid4())


async def _colar(client, token, texto):
    return await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": texto},
    )


async def _resumo(client, token):
    r = await client.get(
        "/api/v1/transacoes/fiscal/resumo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    return r.json()


# ============================================================
# Shape
# ============================================================

async def test_resumo_shape_completo(client):
    token = await _registrar(client)
    body = await _resumo(client, token)
    for campo in (
        "ano_referencia", "faturamento_acumulado", "teto_anual",
        "percentual_consumido", "banda_atual", "ultima_avaliacao_em",
        "faixas", "proxima_faixa", "alertas_nao_lidos",
    ):
        assert campo in body, f"faltando: {campo}"
    assert len(body["faixas"]) == 6


async def test_resumo_sem_jwt_401(client):
    r = await client.get("/api/v1/transacoes/fiscal/resumo")
    assert r.status_code == 401


# ============================================================
# Estado inicial (sem transacoes)
# ============================================================

async def test_resumo_inicial_zerado(client):
    token = await _registrar(client)
    body = await _resumo(client, token)
    assert Decimal(body["faturamento_acumulado"]) == Decimal("0")
    assert body["banda_atual"] is None
    assert body["percentual_consumido"] == 0.0
    assert body["alertas_nao_lidos"] == 0
    assert all(not f["atingida"] for f in body["faixas"])
    assert body["proxima_faixa"]["slug"] == "enq_MEI_60"


# ============================================================
# Apos ingestao de receita
# ============================================================

async def test_resumo_apos_receita_pj(client):
    token = await _registrar(client)
    await _colar(
        client, token,
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 50.000,00",
    )
    body = await _resumo(client, token)
    assert Decimal(body["faturamento_acumulado"]) == Decimal("50000.00")
    assert body["banda_atual"] == "enq_MEI_60"
    # 50000 / 81000 = 0.617
    assert 0.61 < body["percentual_consumido"] < 0.63
    # faixas 60 atingida, 80 nao
    faixas = {f["slug"]: f for f in body["faixas"]}
    assert faixas["enq_MEI_60"]["atingida"] is True
    assert faixas["enq_MEI_80"]["atingida"] is False
    # proxima faixa e 80, com falta calculada
    assert body["proxima_faixa"]["slug"] == "enq_MEI_80"
    assert Decimal(body["proxima_faixa"]["limiar"]) == Decimal("64800.00")
    assert Decimal(body["proxima_faixa"]["falta"]) == Decimal("14800.00")


async def test_resumo_salario_nao_afeta_faturamento(client):
    token = await _registrar(client)
    await _colar(
        client, token,
        "24/09 CREDITO TED FOLHA SALARIO R$ 4.850,00",
    )
    body = await _resumo(client, token)
    assert Decimal(body["faturamento_acumulado"]) == Decimal("0")
    assert body["banda_atual"] is None


async def test_resumo_alerta_nao_lido_conta(client):
    token = await _registrar(client)
    await _colar(
        client, token,
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 50.000,00",
    )
    body = await _resumo(client, token)
    # cruzou 60% -> 1 alerta gerado, nao lido
    assert body["alertas_nao_lidos"] >= 1


async def test_resumo_multiplas_faixas_atingidas(client):
    token = await _registrar(client)
    # 70000 = 86.4% -> cruza 60 e 80
    await _colar(
        client, token,
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 70.000,00",
    )
    body = await _resumo(client, token)
    faixas = {f["slug"]: f for f in body["faixas"]}
    assert faixas["enq_MEI_60"]["atingida"] is True
    assert faixas["enq_MEI_80"]["atingida"] is True
    assert faixas["enq_MEI_90"]["atingida"] is False
    assert body["banda_atual"] == "enq_MEI_80"


# ============================================================
# Isolamento
# ============================================================

async def test_resumo_isolamento_por_usuario(client):
    token_a = await _registrar(client, email="fra@x.com", cpf="444.444.440-10")
    token_b = await _registrar(client, email="frb@x.com", cpf="555.555.550-40")

    await _colar(
        client, token_a,
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 50.000,00",
    )
    body_a = await _resumo(client, token_a)
    body_b = await _resumo(client, token_b)
    assert Decimal(body_a["faturamento_acumulado"]) == Decimal("50000.00")
    assert Decimal(body_b["faturamento_acumulado"]) == Decimal("0")
    assert body_b["banda_atual"] is None
