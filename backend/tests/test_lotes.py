"""Extratos que se sobrepõem, desfazer importação e apagar lançamento.

Revisão de 2026-10-09, achado R12. Reprodução da auditoria: colar a semana
(2 linhas) e depois o mês (as mesmas 2 + 1 nova) gravava 5 lançamentos e o
painel mostrava R$ 2.500 onde o extrato tem R$ 1.500; não havia como apagar.

O identificador da transação continua o do contrato (CONTRATOS_INTERNOS §3):
nada é descartado sozinho. A API conta os prováveis repetidos e a pessoa
decide.
"""
import base64
import uuid
from datetime import date
from decimal import Decimal

from caixaclaro.db import conexao

ANO = date.today().year
CPF_A = "444.444.440-10"
CPF_B = "666.666.660-70"

SEMANA = (
    f"02/01/{ANO} SERVICO PRESTADO CONSULTORIA ACME 1.000,00\n"
    f"03/01/{ANO} VENDA BALCAO 500,00"
)
MES = SEMANA + f"\n20/01/{ANO} SERVICO PRESTADO CONSULTORIA BETA 1.000,00"


def _h(token, idem=False):
    h = {"Authorization": f"Bearer {token}"}
    if idem:
        h["Idempotency-Key"] = str(uuid.uuid4())
    return h


async def _registrar(client, email="lote@x.com", cpf=CPF_A):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha12345", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


async def _colar(client, token, texto):
    r = await client.post(
        "/api/v1/transacoes/extrato/colar", headers=_h(token, True), json={"texto": texto}
    )
    assert r.status_code == 201, r.json()
    return r.json()


async def _faturamento(client, token):
    r = await client.get("/api/v1/transacoes/fiscal/resumo", headers=_h(token))
    return Decimal(r.json()["faturamento_acumulado"])


async def _lancamentos(client, token):
    r = await client.get("/api/v1/transacoes?limite=100", headers=_h(token))
    return r.json()["itens"]


async def test_extrato_sobreposto_avisa_e_apaga_so_os_repetidos(client):
    token = await _registrar(client)
    semana = await _colar(client, token, SEMANA)
    assert semana["importados"] == 2
    assert semana["possiveis_repetidos"] == 0
    assert await _faturamento(client, token) == Decimal("1500.00")

    mes = await _colar(client, token, MES)
    assert mes["importados"] == 3
    assert mes["possiveis_repetidos"] == 2  # aviso, não decisão
    # Sem fazer nada, a soma conta a semana duas vezes: 1.500 + 2.500.
    assert await _faturamento(client, token) == Decimal("4000.00")

    r = await client.delete(
        f"/api/v1/transacoes/lotes/{mes['paste_id']}/repetidos", headers=_h(token)
    )
    assert r.status_code == 200, r.json()
    assert r.json()["apagados"] == 2

    assert await _faturamento(client, token) == Decimal("2500.00")
    descricoes = sorted(t["descricao_bruta"] for t in await _lancamentos(client, token))
    assert descricoes == [
        "SERVICO PRESTADO CONSULTORIA ACME",
        "SERVICO PRESTADO CONSULTORIA BETA",
        "VENDA BALCAO",
    ]
    # Os lançamentos da semana (os de antes) ficaram.
    restantes_semana = [i["id"] for i in semana["itens"]]
    ids = {t["id"] for t in await _lancamentos(client, token)}
    assert set(restantes_semana) <= ids


async def test_repetido_e_contado_como_multiconjunto(client):
    token = await _registrar(client)
    await _colar(client, token, f"05/01/{ANO} COMPRA CAFE DA ESQUINA -5,00")
    novo = await _colar(
        client,
        token,
        f"05/01/{ANO} COMPRA CAFE DA ESQUINA -5,00\n"
        f"05/01/{ANO} COMPRA CAFE DA ESQUINA -5,00",
    )
    # Dois cafés no extrato novo, um no antigo: só um é repetido.
    assert novo["possiveis_repetidos"] == 1
    r = await client.delete(
        f"/api/v1/transacoes/lotes/{novo['paste_id']}/repetidos", headers=_h(token)
    )
    assert r.json()["apagados"] == 1
    assert len(await _lancamentos(client, token)) == 2


async def test_iguais_na_mesma_colagem_nao_sao_repetidos(client):
    token = await _registrar(client)
    r = await _colar(
        client,
        token,
        f"06/01/{ANO} PIX RECEBIDO CLIENTE ANA 10,00\n"
        f"06/01/{ANO} PIX RECEBIDO CLIENTE ANA 10,00",
    )
    assert r["importados"] == 2
    assert r["possiveis_repetidos"] == 0


async def test_apagar_repetidos_mantem_o_que_a_pessoa_ja_respondeu(client):
    token = await _registrar(client)
    antigo = await _colar(client, token, f"07/01/{ANO} PIX RECEBIDO JOAO SILVA 300,00")
    tx = antigo["itens"][0]["id"]
    r = await client.patch(
        f"/api/v1/transacoes/{tx}/confirmar",
        headers=_h(token, True),
        json={"categoria": "receita_servico"},
    )
    assert r.status_code == 200, r.json()

    novo = await _colar(
        client, token,
        f"07/01/{ANO} PIX RECEBIDO JOAO SILVA 300,00\n08/01/{ANO} TARIFA PACOTE -12,00",
    )
    assert novo["possiveis_repetidos"] == 1
    r = await client.delete(
        f"/api/v1/transacoes/lotes/{novo['paste_id']}/repetidos", headers=_h(token)
    )
    assert r.json()["apagados"] == 1

    restantes = {t["id"]: t for t in await _lancamentos(client, token)}
    assert tx in restantes and restantes[tx]["confirmada"] is True
    assert len(restantes) == 2
    assert await _faturamento(client, token) == Decimal("300.00")


async def test_desfazer_colagem_inteira(client):
    token = await _registrar(client)
    r = await _colar(client, token, MES)
    assert await _faturamento(client, token) == Decimal("2500.00")

    resp = await client.delete(f"/api/v1/transacoes/lotes/{r['paste_id']}", headers=_h(token))
    assert resp.status_code == 200, resp.json()
    assert resp.json()["apagados"] == 3
    assert await _lancamentos(client, token) == []
    assert await _faturamento(client, token) == Decimal("0")

    resp = await client.delete(f"/api/v1/transacoes/lotes/{r['paste_id']}", headers=_h(token))
    assert resp.status_code == 404

    # Colar o mesmo texto de novo depois de desfazer volta a gravar.
    assert (await _colar(client, token, MES))["importados"] == 3


async def test_desfazer_arquivo_importado(client):
    token = await _registrar(client)
    csv = (
        "data;descricao;valor\n"
        f"02/01/{ANO};SERVICO PRESTADO CONSULTORIA ACME;1.000,00\n"
    )
    r = await client.post(
        "/api/v1/transacoes/importar",
        headers=_h(token, True),
        json={"formato": "csv", "conteudo_base64": base64.b64encode(csv.encode()).decode()},
    )
    assert r.status_code == 201, r.json()
    import_id = r.json()["import_id"]
    # O mesmo arquivo de novo: repete tudo — e a API avisa.
    r2 = await client.post(
        "/api/v1/transacoes/importar",
        headers=_h(token, True),
        json={"formato": "csv", "conteudo_base64": base64.b64encode(csv.encode()).decode()},
    )
    assert r2.json()["possiveis_repetidos"] == 1

    resp = await client.delete(f"/api/v1/transacoes/lotes/{import_id}", headers=_h(token))
    assert resp.json()["apagados"] == 1
    assert len(await _lancamentos(client, token)) == 1
    assert await _faturamento(client, token) == Decimal("1000.00")


async def test_apagar_um_lancamento(client):
    token = await _registrar(client)
    r = await _colar(client, token, MES)
    alvo = next(i for i in r["itens"] if "BETA" in i["descricao_bruta"])

    resp = await client.delete(f"/api/v1/transacoes/{alvo['id']}", headers=_h(token))
    assert resp.status_code == 200, resp.json()
    assert resp.json() == {"apagados": 1, "ids": [alvo["id"]]}
    assert await _faturamento(client, token) == Decimal("1500.00")
    assert len(await _lancamentos(client, token)) == 2

    resp = await client.delete(f"/api/v1/transacoes/{alvo['id']}", headers=_h(token))
    assert resp.status_code == 404
    resp = await client.delete("/api/v1/transacoes/nao-e-uuid", headers=_h(token))
    assert resp.status_code == 400

    async with conexao() as conn:
        meta = await conn.fetchval(
            "SELECT meta FROM audit_log WHERE acao = 'transacao_apagada'"
        )
    assert meta is not None and "BETA" not in str(meta)  # sem a descrição


async def test_lancamento_do_banco_conectado_nao_e_apagado(client):
    token = await _registrar(client)
    async with conexao() as conn:
        uid = await conn.fetchval("SELECT id FROM users WHERE email = 'lote@x.com'")
        tx = await conn.fetchval(
            """
            INSERT INTO transactions
              (user_id, origem, pluggy_tx_id, data, descricao_bruta, valor)
            VALUES ($1, 'pluggy', 'px-1', $2, 'PIX RECEBIDO', 10.00)
            RETURNING id
            """,
            uid, date(ANO, 1, 9),
        )
    resp = await client.delete(f"/api/v1/transacoes/{tx}", headers=_h(token))
    assert resp.status_code == 409, resp.json()
    assert resp.json()["erro"] == "ORIGEM_BANCARIA"


async def test_ninguem_apaga_nem_desfaz_o_que_e_de_outra_conta(client):
    token_a = await _registrar(client)
    token_b = await _registrar(client, email="lote-b@x.com", cpf=CPF_B)
    a = await _colar(client, token_a, MES)
    b = await _colar(client, token_b, MES)
    # O mesmo texto gera o mesmo paste_id nas duas contas.
    assert a["paste_id"] == b["paste_id"]

    resp = await client.delete(f"/api/v1/transacoes/{a['itens'][0]['id']}", headers=_h(token_b))
    assert resp.status_code == 404

    resp = await client.delete(f"/api/v1/transacoes/lotes/{b['paste_id']}", headers=_h(token_b))
    assert resp.json()["apagados"] == 3
    assert len(await _lancamentos(client, token_a)) == 3
    assert await _faturamento(client, token_a) == Decimal("2500.00")


async def test_tela_do_lancamento_sabe_a_origem(client):
    """A tela só oferece "Apagar" para o que não veio do banco conectado."""
    token = await _registrar(client)
    r = await _colar(client, token, f"02/01/{ANO} VENDA BALCAO 500,00")
    tx = r["itens"][0]["id"]
    resp = await client.get(f"/api/v1/transacoes/{tx}/opiniao", headers=_h(token))
    assert resp.json()["origem"] == "paste"
