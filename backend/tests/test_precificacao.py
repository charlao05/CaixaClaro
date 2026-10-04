"""Testes de API — precificação (M11), Categoria I da consulta ao CRC-ES."""
import uuid

from tests._cpf import cpf_valido


async def _registrar(client, email_prefix: str) -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{email_prefix}@x.com",
            "senha": "senha123",
            "cpf": cpf_valido(str(uuid.uuid4().int)[:9]),
        },
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


async def test_calcular_um_cenario_completo(client):
    token = await _registrar(client, "prec-completo")
    r = await client.post(
        "/api/v1/precificacao/calcular",
        json={"cenarios": [{
            "nome": "Preço atual", "preco": "50", "custo_variavel_unitario": "30",
            "custos_fixos_periodo": "2000",
        }]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    assert len(body["cenarios"]) == 1
    nomes = {c["nome"] for c in body["cenarios"][0]["calculos"]}
    assert {
        "diferenca_preco_custo",
        "margem_contribuicao_unitaria_reais",
        "margem_contribuicao_unitaria_percentual",
        "ponto_equilibrio_unidades",
        "ponto_equilibrio_receita",
    } <= nomes
    assert body["comparacao"] is None


async def test_toda_saida_tem_estado(client):
    token = await _registrar(client, "prec-estado")
    r = await client.post(
        "/api/v1/precificacao/calcular",
        json={"cenarios": [{
            "nome": "A", "preco": "50", "custo_variavel_unitario": "30",
        }]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    for calc in r.json()["cenarios"][0]["calculos"]:
        assert calc["estado"] in ("calculo", "limitacao")
        assert calc.get("formula")


async def test_comparacao_dois_cenarios_sem_indicar_preferencia(client):
    token = await _registrar(client, "prec-comparacao")
    r = await client.post(
        "/api/v1/precificacao/calcular",
        json={"cenarios": [
            {"nome": "Preço A", "preco": "50", "custo_variavel_unitario": "30"},
            {"nome": "Preço B", "preco": "60", "custo_variavel_unitario": "30"},
        ]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    assert len(body["cenarios"]) == 2
    assert body["comparacao"] is not None
    texto = body["comparacao"].lower()
    assert "sem indicar" in texto or "não indica" in texto or "nao indica" in texto
    bruto = str(body).lower()
    for proibido in ("recomend", "melhor opç", "escolha esta", "deveria"):
        assert proibido not in bruto


async def test_recusa_sem_preco_422(client):
    token = await _registrar(client, "prec-sem-preco")
    r = await client.post(
        "/api/v1/precificacao/calcular",
        json={"cenarios": [{"nome": "A", "custo_variavel_unitario": "30"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


async def test_recusa_custo_negativo(client):
    token = await _registrar(client, "prec-custo-neg")
    r = await client.post(
        "/api/v1/precificacao/calcular",
        json={"cenarios": [
            {"nome": "A", "preco": "50", "custo_variavel_unitario": "-10"}
        ]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code in (400, 422)


async def test_mais_de_dois_cenarios_rejeitado(client):
    token = await _registrar(client, "prec-tres-cenarios")
    r = await client.post(
        "/api/v1/precificacao/calcular",
        json={"cenarios": [
            {"nome": "A", "preco": "10", "custo_variavel_unitario": "5"},
            {"nome": "B", "preco": "20", "custo_variavel_unitario": "5"},
            {"nome": "C", "preco": "30", "custo_variavel_unitario": "5"},
        ]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


async def test_salvar_cenario_persiste_como_hipotese(client):
    token = await _registrar(client, "prec-salvar")
    headers = {"Authorization": f"Bearer {token}"}

    produto = await client.post(
        "/api/v1/produtos", json={"tipo": "produto", "nome": "X"}, headers=headers,
    )
    produto_id = produto.json()["id"]

    r = await client.post(
        "/api/v1/precificacao/calcular",
        json={
            "cenarios": [{"nome": "A", "preco": "50", "custo_variavel_unitario": "30"}],
            "salvar": True, "product_id": produto_id,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.json()
    assert r.json()["cenarios"][0]["calculos"][0]["estado"] == "calculo"


async def test_sem_autenticacao_401(client):
    r = await client.post(
        "/api/v1/precificacao/calcular",
        json={"cenarios": [{"nome": "A", "preco": "10", "custo_variavel_unitario": "5"}]},
    )
    assert r.status_code in (401, 403)