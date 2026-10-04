"""Testes de API — CRUD de produtos/serviços (M11)."""
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


async def test_criar_produto(client):
    token = await _registrar(client, "prod-criar")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/produtos",
        json={
            "tipo": "produto", "nome": "Camiseta P",
            "unidade_medida": "un", "custo_atual": "18.00", "preco_atual": "49.90",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["nome"] == "Camiseta P"
    assert body["custo_atual"] == "18.00"
    assert body["ativo"] is True


async def test_criar_produto_sem_autenticacao_401(client):
    r = await client.post(
        "/api/v1/produtos",
        json={"tipo": "produto", "nome": "X"},
    )
    assert r.status_code in (401, 403)


async def test_listar_produtos_vazio(client):
    token = await _registrar(client, "prod-vazio")
    r = await client.get(
        "/api/v1/produtos", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == {"itens": []}


async def test_listar_produtos_isolamento_por_usuario(client):
    token_a = await _registrar(client, "prod-iso-a")
    token_b = await _registrar(client, "prod-iso-b")

    await client.post(
        "/api/v1/produtos",
        json={"tipo": "servico", "nome": "Corte de cabelo"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    r = await client.get(
        "/api/v1/produtos", headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.json() == {"itens": []}

    r = await client.get(
        "/api/v1/produtos", headers={"Authorization": f"Bearer {token_a}"},
    )
    assert len(r.json()["itens"]) == 1


async def test_obter_produto_de_outro_usuario_404(client):
    token_a = await _registrar(client, "prod-outro-a")
    token_b = await _registrar(client, "prod-outro-b")

    r = await client.post(
        "/api/v1/produtos",
        json={"tipo": "produto", "nome": "Caneca"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    produto_id = r.json()["id"]

    r = await client.get(
        f"/api/v1/produtos/{produto_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
    assert r.json()["erro"] == "PRODUTO_NAO_ENCONTRADO"


async def test_atualizar_produto_patch_parcial(client):
    token = await _registrar(client, "prod-patch")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/produtos",
        json={"tipo": "produto", "nome": "Boné", "preco_atual": "40.00"},
        headers=headers,
    )
    produto_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/produtos/{produto_id}",
        json={"preco_atual": "45.00"},
        headers=headers,
    )
    assert r.status_code == 200, r.json()
    assert r.json()["preco_atual"] == "45.00"
    assert r.json()["nome"] == "Boné"  # campo não enviado permanece


async def test_tipo_invalido_rejeitado(client):
    token = await _registrar(client, "prod-tipo-invalido")
    r = await client.post(
        "/api/v1/produtos",
        json={"tipo": "outra-coisa", "nome": "X"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


async def test_campo_extra_rejeitado(client):
    """ConfigDict(extra='forbid') — contrato estrito, igual ao resto da API."""
    token = await _registrar(client, "prod-extra")
    r = await client.post(
        "/api/v1/produtos",
        json={"tipo": "produto", "nome": "X", "campo_que_nao_existe": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422