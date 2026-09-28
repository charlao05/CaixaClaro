"""Testes end-to-end M4b via HTTP (N8).

Os testes em test_integracao_fiscal.py exercitam funcoes puras:
  conta_faturamento, faixa_cruzada, calcular_delta, processar_lancamento.

Aqui, exercitamos o endpoint POST /extrato/colar e verificamos o que
foi de fato persistido: transactions, fiscal_state, alerts.

Cada teste cobre exatamente uma invariante do §9 e §10 do contrato.
"""
import json
import uuid
from decimal import Decimal

from caixaclaro.db import conexao


async def _registrar(
    client, email: str = "f@x.com", cpf: str = "111.111.111-11"
) -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


def _key() -> str:
    return str(uuid.uuid4())


async def _colar(client, token: str, texto: str, *, key: str | None = None):
    return await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": key or _key(),
        },
        json={"texto": texto},
    )


# ============================================================
# 1. Classificacao persiste em transactions
# ============================================================

async def test_colar_persiste_categoria_e_triagem(client):
    token = await _registrar(client)
    r = await _colar(
        client, token, "25/09 PAGTO GUIA DAS SIMPLES R$ 100,00"
    )
    assert r.status_code == 201, r.json()

    async with conexao() as conn:
        row = await conn.fetchrow(
            """
            SELECT categoria, proposito, needs_review
            FROM transactions
            WHERE origem = 'paste'
            """
        )

    assert row is not None
    assert row["categoria"] == "imposto_das"
    assert row["proposito"] is not None
    assert row["needs_review"] is False


# ============================================================
# 2. Receita de negocio incrementa fiscal_state
# ============================================================

async def test_colar_receita_negocio_incrementa_fiscal_state(client):
    token = await _registrar(client)
    r = await _colar(
        client, token,
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 500,00",
    )
    assert r.status_code == 201, r.json()

    async with conexao() as conn:
        cat = await conn.fetchval(
            "SELECT categoria FROM transactions WHERE origem = 'paste'"
        )
        estado_raw = await conn.fetchval("SELECT estado FROM fiscal_state")

    assert cat == "receita_servico"
    assert estado_raw is not None
    estado = json.loads(estado_raw) if isinstance(estado_raw, str) else estado_raw
    assert Decimal(estado["faturamento_acumulado"]) == Decimal("500.00")


# ============================================================
# 3. Salario nao incrementa fiscal_state
# ============================================================

async def test_colar_salario_nao_incrementa_fiscal_state(client):
    token = await _registrar(client)
    r = await _colar(
        client, token,
        "24/09 CREDITO TED FOLHA SALARIO R$ 3.000,00",
    )
    assert r.status_code == 201, r.json()

    async with conexao() as conn:
        cat = await conn.fetchval(
            "SELECT categoria FROM transactions WHERE origem = 'paste'"
        )
        estado_raw = await conn.fetchval("SELECT estado FROM fiscal_state")

    assert cat == "salario"
    if estado_raw is not None:
        estado = json.loads(estado_raw) if isinstance(estado_raw, str) else estado_raw
        fat = estado.get("faturamento_acumulado", "0")
        assert Decimal(fat) == Decimal("0")


# ============================================================
# 4. Cruzamento de faixa gera alerta
# ============================================================

async def test_colar_cruza_60_gera_alerta(client):
    token = await _registrar(client)
    r = await _colar(
        client, token,
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 50.000,00",
    )
    assert r.status_code == 201, r.json()

    async with conexao() as conn:
        rows = await conn.fetch(
            """
            SELECT banda_ou_slug, severidade
            FROM alerts
            WHERE tipo = 'faturamento_faixa'
            """
        )

    slugs = {r["banda_ou_slug"] for r in rows}
    assert "enq_MEI_60" in slugs

    sev = [
        r["severidade"] for r in rows if r["banda_ou_slug"] == "enq_MEI_60"
    ]
    assert sev == ["informativo"]


# ============================================================
# 5. Replay nao duplica alerta
# ============================================================

async def test_colar_replay_nao_duplica_alerta(client):
    token = await _registrar(client)
    texto = "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 50.000,00"

    r1 = await _colar(client, token, texto)
    r2 = await _colar(client, token, texto)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["importados"] == 1
    assert r2.json()["importados"] == 0
    assert r1.json()["paste_id"] == r2.json()["paste_id"]

    async with conexao() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM alerts WHERE banda_ou_slug = 'enq_MEI_60'"
        )
    assert n == 1


# ============================================================
# 6. Duas receitas no mesmo usuario somam no fiscal_state
#    (bug latente: JSONB volta como str; _load_estado normaliza)
# ============================================================

async def test_duas_receitas_somam_no_fiscal_state(client):
    token = await _registrar(client)

    r1 = await _colar(
        client, token,
        "25/09 CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA R$ 500,00",
    )
    r2 = await _colar(
        client, token,
        "26/09 VENDA BALCAO R$ 300,00",
    )
    assert r1.status_code == 201, r1.json()
    assert r2.status_code == 201, r2.json()
    assert r1.json()["importados"] == 1
    assert r2.json()["importados"] == 1

    async with conexao() as conn:
        estado_raw = await conn.fetchval("SELECT estado FROM fiscal_state")

    estado = json.loads(estado_raw) if isinstance(estado_raw, str) else estado_raw
    assert Decimal(estado["faturamento_acumulado"]) == Decimal("800.00")



# ============================================================
# 7. Importacao CSV passa pelo mesmo pipeline fiscal do colar
# ============================================================

async def test_importar_csv_persiste_classificacao_e_fiscal_state(client):
    token = await _registrar(
        client,
        email="csv-fiscal@x.com",
        cpf="222.222.222-22",
    )

    import base64

    csv_bytes = (
        "data;descricao;valor\n"
        "25/09/2026;CREDITO LIQUIDO SERVICO AGENCIA DIG LTDA;500,00\n"
    ).encode("utf-8")

    r = await client.post(
        "/api/v1/transacoes/importar",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": _key(),
        },
        json={
            "formato": "csv",
            "conteudo_base64": base64.b64encode(csv_bytes).decode("ascii"),
        },
    )

    assert r.status_code == 201, r.json()

    async with conexao() as conn:
        row = await conn.fetchrow(
            """
            SELECT categoria, proposito, needs_review
            FROM transactions
            WHERE user_id = (
                SELECT id FROM users WHERE email = 'csv-fiscal@x.com'
            )
              AND origem = 'csv'
            """
        )
        estado_raw = await conn.fetchval(
            """
            SELECT estado
            FROM fiscal_state
            WHERE user_id = (
                SELECT id FROM users WHERE email = 'csv-fiscal@x.com'
            )
            """
        )

    assert row is not None
    assert row["categoria"] == "receita_servico"
    assert row["proposito"] is not None
    assert row["needs_review"] is False

    assert estado_raw is not None
    estado = (
        json.loads(estado_raw)
        if isinstance(estado_raw, str)
        else estado_raw
    )
    assert Decimal(estado["faturamento_acumulado"]) == Decimal("500.00")