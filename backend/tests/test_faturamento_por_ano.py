"""O faturamento do ano é a soma dos lançamentos gravados daquele ano.

Defeito encontrado na revisão de 2026-10-09 (docs/AUDITORIA_JORNADA_2026-10-09.md,
seção 8, achado R5), reproduzido no main @ 2215b7e e no M13:

  - colar um extrato do ano anterior depois de já ter o ano corrente trocava
    o ano do painel e zerava o acumulado; o lançamento seguinte do ano
    corrente recomeçava do zero;
  - uma colagem que atravessava a virada do ano somava tudo no ano mais novo;
  - no M13, confirmar como trabalho um Pix do ano anterior fazia o mesmo.

M4_CONTRATO §9 define `faturamento_acumulado` como a "soma atual das
transações do usuário"; a implementação mantinha um contador por deltas, que
se perdia. Agora a soma é lida do banco, por ano-calendário.
"""
import base64
import itertools
import json
import uuid
from datetime import date
from decimal import Decimal

from caixaclaro.db import conexao
from caixaclaro.domain.fiscal.taxonomia import CATEGORIAS
from caixaclaro.services.faturamento import (
    ano_de_referencia,
    conta_faturamento,
    somar_faturamento_do_ano,
)

ANO = date.today().year
ANTERIOR = ANO - 1
SEGUINTE = ANO + 1


def _h(token: str, *, idem: bool = False) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if idem:
        h["Idempotency-Key"] = str(uuid.uuid4())
    return h


async def _registrar(client, email="ano@x.com", cpf="444.444.440-10", regime="MEI"):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha12345", "cpf": cpf, "regime": regime},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"], uuid.UUID(r.json()["user"]["id"])


async def _colar(client, token, texto):
    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers=_h(token, idem=True),
        json={"texto": texto},
    )
    assert r.status_code == 201, r.json()
    return r.json()


async def _resumo(client, token):
    r = await client.get("/api/v1/transacoes/fiscal/resumo", headers=_h(token))
    assert r.status_code == 200, r.json()
    return r.json()


async def _retrato(uid):
    async with conexao() as conn:
        bruto = await conn.fetchval(
            "SELECT estado FROM fiscal_state WHERE user_id = $1", uid
        )
    if bruto is None:
        return None
    return json.loads(bruto) if isinstance(bruto, str) else dict(bruto)


# ---------------------------------------------------------------------------
# A soma em SQL e a regra em Python dizem a mesma coisa
# ---------------------------------------------------------------------------

async def test_soma_em_sql_e_regra_em_python_concordam(client):
    _, uid = await _registrar(client)
    patrimonios = (
        "pessoa_fisica", "atividade_negocio", "ponte_pf_pj", "transito_terceiro", None,
    )
    categorias = tuple(CATEGORIAS) + (None,)
    valores = (Decimal("-10.00"), Decimal("0.00"), Decimal("10.00"))

    esperado = Decimal("0")
    async with conexao() as conn:
        for patrimonio, categoria, valor in itertools.product(
            patrimonios, categorias, valores
        ):
            await conn.execute(
                """
                INSERT INTO transactions
                  (user_id, origem, data, descricao_bruta, valor, categoria, patrimonio)
                VALUES ($1, 'manual', $2, 'combinacao', $3, $4, $5)
                """,
                uid, date(ANO, 3, 10), valor, categoria, patrimonio,
            )
            if conta_faturamento(patrimonio, categoria, valor):
                esperado += valor
        soma = await somar_faturamento_do_ano(conn, uid, ANO)

    assert esperado == Decimal("20.00")  # só receita de negócio, positiva
    assert soma == esperado


async def test_soma_respeita_as_bordas_do_ano(client):
    _, uid = await _registrar(client)
    async with conexao() as conn:
        for dia, valor in (
            (date(ANTERIOR, 12, 31), "1.00"),
            (date(ANO, 1, 1), "2.00"),
            (date(ANO, 12, 31), "4.00"),
            (date(SEGUINTE, 1, 1), "8.00"),
        ):
            await conn.execute(
                """
                INSERT INTO transactions
                  (user_id, origem, data, descricao_bruta, valor, categoria, patrimonio)
                VALUES ($1, 'manual', $2, 'borda', $3, 'receita_servico', 'atividade_negocio')
                """,
                uid, dia, Decimal(valor),
            )
        assert await somar_faturamento_do_ano(conn, uid, ANTERIOR) == Decimal("1.00")
        assert await somar_faturamento_do_ano(conn, uid, ANO) == Decimal("6.00")
        assert await somar_faturamento_do_ano(conn, uid, SEGUINTE) == Decimal("8.00")


# ---------------------------------------------------------------------------
# As três reproduções
# ---------------------------------------------------------------------------

async def test_extrato_do_ano_anterior_nao_apaga_o_ano_corrente(client):
    token, uid = await _registrar(client)

    await _colar(client, token, f"10/02/{ANO} SERVICO PRESTADO CONSULTORIA ACME 50.000,00")
    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("50000.00")

    # Depois, um extrato do ano anterior.
    await _colar(client, token, f"10/12/{ANTERIOR} SERVICO PRESTADO CONSULTORIA BETA 1.000,00")
    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("50000.00")

    # E de novo um lançamento do ano corrente: soma, não recomeça.
    await _colar(client, token, f"11/02/{ANO} SERVICO PRESTADO CONSULTORIA GAMA 100,00")
    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("50100.00")

    retrato = await _retrato(uid)
    assert retrato["ano_referencia"] == ANO
    assert Decimal(retrato["faturamento_acumulado"]) == Decimal("50100.00")

    async with conexao() as conn:
        assert await somar_faturamento_do_ano(conn, uid, ANTERIOR) == Decimal("1000.00")


async def test_colagem_que_atravessa_a_virada_soma_cada_lancamento_no_seu_ano(client):
    token, uid = await _registrar(client)
    await _colar(
        client, token,
        f"30/12/{ANTERIOR} SERVICO PRESTADO CONSULTORIA DELTA 700,00\n"
        f"02/01/{ANO} SERVICO PRESTADO CONSULTORIA DELTA 300,00",
    )
    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("300.00")
    async with conexao() as conn:
        assert await somar_faturamento_do_ano(conn, uid, ANTERIOR) == Decimal("700.00")


async def test_confirmar_lancamento_do_ano_anterior_nao_troca_o_ano_do_painel(client):
    token, uid = await _registrar(client)
    await _colar(client, token, f"10/02/{ANO} SERVICO PRESTADO CONSULTORIA ACME 1.100,00")
    await _colar(client, token, f"20/12/{ANTERIOR} PIX RECEBIDO FULANO DE TAL 200,00")

    r = await client.get("/api/v1/transacoes/fila?limite=10", headers=_h(token))
    item = r.json()["itens"][0]
    r = await client.patch(
        f"/api/v1/transacoes/{item['id']}/confirmar",
        headers=_h(token, idem=True),
        json={"categoria": "receita_servico"},
    )
    assert r.status_code == 200, r.json()
    assert Decimal(r.json()["delta_faturamento"]) == Decimal("200.00")

    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("1100.00")
    async with conexao() as conn:
        assert await somar_faturamento_do_ano(conn, uid, ANTERIOR) == Decimal("200.00")


# ---------------------------------------------------------------------------
# Ano de referência
# ---------------------------------------------------------------------------

async def test_sem_lancamento_o_painel_e_do_ano_corrente(client):
    token, uid = await _registrar(client)
    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("0")
    async with conexao() as conn:
        assert await ano_de_referencia(conn, uid) == ANO


async def test_quem_so_trouxe_o_ano_anterior_ve_o_ano_anterior(client):
    token, _ = await _registrar(client)
    await _colar(client, token, f"10/12/{ANTERIOR} SERVICO PRESTADO CONSULTORIA BETA 1.000,00")
    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANTERIOR
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("1000.00")


async def test_data_no_futuro_nao_puxa_o_painel_para_o_ano_seguinte(client):
    token, uid = await _registrar(client)
    await _colar(client, token, f"10/02/{ANO} SERVICO PRESTADO CONSULTORIA ACME 900,00")
    await _colar(client, token, f"10/01/{SEGUINTE} SERVICO PRESTADO CONSULTORIA ACME 50,00")

    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("900.00")
    retrato = await _retrato(uid)
    assert retrato["ano_referencia"] == ANO
    assert Decimal(retrato["faturamento_acumulado"]) == Decimal("900.00")


async def test_painel_soma_o_que_esta_gravado_mesmo_com_o_retrato_errado(client):
    token, uid = await _registrar(client)
    await _colar(client, token, f"10/02/{ANO} SERVICO PRESTADO CONSULTORIA ACME 900,00")
    async with conexao() as conn:
        await conn.execute(
            "UPDATE fiscal_state SET estado = $2::jsonb WHERE user_id = $1",
            uid,
            json.dumps({"faturamento_acumulado": "123456.78", "ano_referencia": 1999}),
        )
    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("900.00")
    assert resumo["banda_atual"] is None


# ---------------------------------------------------------------------------
# Alertas de faixa são do ano do lançamento (M4_CONTRATO §10)
# ---------------------------------------------------------------------------

async def _alertas(uid):
    async with conexao() as conn:
        rows = await conn.fetch(
            "SELECT banda_ou_slug, prazo, mensagem FROM alerts WHERE user_id = $1 "
            "ORDER BY prazo, banda_ou_slug",
            uid,
        )
    return [(r["banda_ou_slug"], r["prazo"], r["mensagem"]) for r in rows]


async def test_alerta_de_faixa_e_do_ano_do_lancamento(client):
    token, uid = await _registrar(client)
    await _colar(client, token, f"10/02/{ANO} SERVICO PRESTADO CONSULTORIA ACME 1.000,00")
    await _colar(client, token, f"10/11/{ANTERIOR} SERVICO PRESTADO CONSULTORIA BETA 50.000,00")

    alertas = await _alertas(uid)
    assert [(slug, prazo) for slug, prazo, _ in alertas] == [
        ("enq_MEI_60", date(ANTERIOR, 12, 31)),
    ]
    assert f"de {ANTERIOR}" in alertas[0][2]
    # O painel continua no ano corrente, com a soma do ano corrente.
    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("1000.00")


async def test_varias_confirmacoes_pequenas_cruzam_a_faixa_e_avisam_uma_vez(client):
    """Seis respostas de R$ 10.000 levam a soma de 0 a 60.000 (74% do limite).
    O aviso de 60% tem de existir, uma única vez."""
    token, uid = await _registrar(client)
    linhas = "\n".join(
        f"{dia:02d}/02/{ANO} PIX RECEBIDO CLIENTE NUMERO {dia} 10.000,00"
        for dia in range(1, 7)
    )
    await _colar(client, token, linhas)
    r = await client.get("/api/v1/transacoes/fila?limite=10", headers=_h(token))
    for item in r.json()["itens"]:
        r = await client.patch(
            f"/api/v1/transacoes/{item['id']}/confirmar",
            headers=_h(token, idem=True),
            json={"categoria": "receita_servico"},
        )
        assert r.status_code == 200, r.json()

    assert [slug for slug, _, _ in await _alertas(uid)] == ["enq_MEI_60"]
    assert Decimal((await _resumo(client, token))["faturamento_acumulado"]) == Decimal("60000.00")


async def test_aviso_que_faltou_e_registrado_na_proxima_escrita_do_ano(client):
    """§10: "avalia qual faixa corresponde ao faturamento atual e insere o
    alerta se ainda não existir para aquele prazo"."""
    token, uid = await _registrar(client)
    async with conexao() as conn:
        await conn.execute(
            """
            INSERT INTO transactions
              (user_id, origem, data, descricao_bruta, valor, categoria, patrimonio)
            VALUES ($1, 'manual', $2, 'gravado sem passar pelo servico', 50000.00,
                    'receita_servico', 'atividade_negocio')
            """,
            uid, date(ANO, 2, 1),
        )
    assert await _alertas(uid) == []
    # O painel já mostra a soma certa, mesmo sem nenhuma escrita pelo serviço.
    assert Decimal((await _resumo(client, token))["faturamento_acumulado"]) == Decimal("50000.00")

    await _colar(client, token, f"02/02/{ANO} SERVICO PRESTADO CONSULTORIA ACME 10,00")
    assert [slug for slug, _, _ in await _alertas(uid)] == ["enq_MEI_60"]


async def test_quem_nao_e_mei_nao_recebe_alerta_em_nenhum_ano(client):
    token, uid = await _registrar(client, regime="PF")
    await _colar(
        client, token,
        f"10/11/{ANTERIOR} SERVICO PRESTADO REFORMA DONA LUCIA 70.000,00\n"
        f"10/02/{ANO} SERVICO PRESTADO REFORMA DONA LUCIA 70.000,00",
    )
    assert await _alertas(uid) == []
    resumo = await _resumo(client, token)
    assert resumo["teto_anual"] is None
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("70000.00")


# ---------------------------------------------------------------------------
# Importação por arquivo segue a mesma regra
# ---------------------------------------------------------------------------

async def test_arquivo_que_atravessa_a_virada_soma_por_ano(client):
    token, uid = await _registrar(client)
    csv = (
        "data;descricao;valor\n"
        f"30/12/{ANTERIOR};SERVICO PRESTADO CONSULTORIA DELTA;700,00\n"
        f"02/01/{ANO};SERVICO PRESTADO CONSULTORIA DELTA;300,00\n"
    )
    r = await client.post(
        "/api/v1/transacoes/importar",
        headers=_h(token, idem=True),
        json={"formato": "csv", "conteudo_base64": base64.b64encode(csv.encode()).decode()},
    )
    assert r.status_code == 201, r.json()
    assert r.json()["importados"] == 2

    resumo = await _resumo(client, token)
    assert resumo["ano_referencia"] == ANO
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("300.00")
    async with conexao() as conn:
        assert await somar_faturamento_do_ano(conn, uid, ANTERIOR) == Decimal("700.00")
