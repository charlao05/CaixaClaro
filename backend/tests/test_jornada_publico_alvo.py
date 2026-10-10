"""Jornadas do público-alvo — critérios de aceite de produto (Fase 0).

Cada teste descreve, pela API real, um comportamento que um MEI ou autônomo
precisa encontrar ao usar o CaixaClaro com um extrato de verdade.

Estado em 2026-10-09 (main @ 2215b7e, PostgreSQL 16): os 12 testes abaixo
FALHAM. Evidência e contexto em docs/AUDITORIA_JORNADA_2026-10-09.md.

Por isso cada um carrega `xfail(strict=True)`:
  - enquanto o defeito existir, a suíte continua verde e o defeito fica
    registrado com nome e motivo (não escondido);
  - quando a correção entrar, o teste passa, o xfail estrito acusa XPASS e
    a suíte quebra até o marcador ser removido. O status só muda com evidência.

Os testes J4, J8 e J9 pressupõem decisões de contrato ainda NÃO aprovadas
(D2, D4 e D5 na auditoria). Se a decisão for outra, o teste muda junto.
"""
import base64
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest


CPF = "444.444.440-10"


def _falha_conhecida(achado: str, motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"{achado}: {motivo}")


def _h(token: str, *, idem: bool = False) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if idem:
        h["Idempotency-Key"] = str(uuid.uuid4())
    return h


async def _registrar(client, email: str = "jornada@x.com") -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha12345", "cpf": CPF},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


async def _colar(client, token: str, texto: str):
    return await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers=_h(token, idem=True),
        json={"texto": texto},
    )


async def _transacoes(client, token: str) -> list[dict]:
    r = await client.get("/api/v1/transacoes?limite=100", headers=_h(token))
    assert r.status_code == 200, r.json()
    return r.json()["itens"]


async def _fila(client, token: str) -> list[dict]:
    r = await client.get("/api/v1/transacoes/fila?limite=100", headers=_h(token))
    assert r.status_code == 200, r.json()
    return r.json()["itens"]


async def _confirmar(client, token: str, tx_id: str, categoria: str):
    return await client.patch(
        f"/api/v1/transacoes/{tx_id}/confirmar",
        headers=_h(token, idem=True),
        json={"categoria": categoria},
    )


async def _resumo(client, token: str) -> dict:
    r = await client.get("/api/v1/transacoes/fiscal/resumo", headers=_h(token))
    assert r.status_code == 200, r.json()
    return r.json()


async def _opiniao(client, token: str, tx_id: str) -> dict:
    r = await client.get(f"/api/v1/transacoes/{tx_id}/opiniao", headers=_h(token))
    assert r.status_code == 200, r.json()
    return r.json()


_TEXTOS_DO_PARECER = (
    "fato",
    "interpretacao",
    "relacao_pf_pj",
    "possivel_tratamento_tributario",
    "condicoes_necessarias",
    "pendencias",
    "proximo_passo",
)


# ---------------------------------------------------------------------------
# A1 — a receita que o usuário confirma precisa contar
# ---------------------------------------------------------------------------

async def test_j1_pix_confirmado_como_trabalho_conta_no_faturamento(client):
    token = await _registrar(client)
    r = await _colar(
        client, token, "25/09 PIX RECEBIDO UBER DO BRASIL TECNOLOGIA LTDA 612,40"
    )
    assert r.status_code == 201, r.json()

    item = (await _fila(client, token))[0]
    r = await _confirmar(client, token, item["id"], "receita_servico")
    assert r.status_code == 200, r.json()

    assert Decimal(r.json()["delta_faturamento"]) == Decimal("612.40")
    resumo = await _resumo(client, token)
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("612.40")


# ---------------------------------------------------------------------------
# A2 — o que o usuário lê não pode vazar vocabulário interno nem se contradizer
# ---------------------------------------------------------------------------

async def test_j2_parecer_nao_vaza_jargao_interno(client):
    token = await _registrar(client)
    await _colar(client, token, "25/09 PIX RECEBIDO JOAO DA SILVA 100,00")
    item = (await _fila(client, token))[0]
    await _confirmar(client, token, item["id"], "receita_servico")

    opiniao = await _opiniao(client, token, item["id"])
    for campo in _TEXTOS_DO_PARECER:
        texto = opiniao[campo]
        assert "Guardrail" not in texto, (campo, texto)
        assert "None" not in texto, (campo, texto)
        assert "§" not in texto, (campo, texto)


async def test_j3_transacao_confirmada_recebe_selo_de_confirmada(client):
    token = await _registrar(client)
    await _colar(client, token, "25/09 PIX RECEBIDO JOAO DA SILVA 100,00")
    item = (await _fila(client, token))[0]
    await _confirmar(client, token, item["id"], "receita_servico")

    opiniao = await _opiniao(client, token, item["id"])
    assert opiniao["confirmada"] is True
    assert opiniao["grau_certeza_leitura"] == "fato_confirmado"


# ---------------------------------------------------------------------------
# A3 — "quando não dá para saber, ele pergunta"
# ---------------------------------------------------------------------------

async def test_j4_palpite_sem_confirmacao_nao_recebe_selo_de_fato(client):
    token = await _registrar(client)
    await _colar(client, token, "10/09 PAGAMENTO DE BOLETO CLARO S.A. -59,90")
    tx = (await _transacoes(client, token))[0]

    opiniao = await _opiniao(client, token, tx["id"])
    assert opiniao["confirmada"] is False
    assert opiniao["grau_certeza_leitura"] != "fato_confirmado"


async def test_j5_saida_nunca_e_apresentada_como_entrada(client):
    token = await _registrar(client)
    await _colar(
        client, token, "12/09 PIX ENVIADO PAGAMENTO SALARIO FUNCIONARIA ANA -1.621,00"
    )
    tx = (await _transacoes(client, token))[0]

    opiniao = await _opiniao(client, token, tx["id"])
    assert not opiniao["fato"].startswith("Entrada"), opiniao["fato"]


async def test_j6_entrada_nunca_vira_despesa_em_silencio(client):
    token = await _registrar(client)
    await _colar(client, token, "13/09 PIX RECEBIDO ANA CLARO MENDES 150,00")
    tx = (await _transacoes(client, token))[0]

    virou_despesa_sem_perguntar = (
        tx["categoria"] == "custo_operacional" and tx["needs_review"] is False
    )
    assert not virou_despesa_sem_perguntar, tx


async def test_j7_despesa_nunca_reduz_faturamento(client):
    token = await _registrar(client)
    r = await _colar(
        client,
        token,
        "10/09 SERVICO PRESTADO CONSULTORIA ACME 1.000,00\n"
        "11/09 PIX ENVIADO CONSULTORIA CONTABIL DO BAIRRO -400,00",
    )
    assert r.status_code == 201, r.json()

    resumo = await _resumo(client, token)
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("1000.00")


# ---------------------------------------------------------------------------
# A4 — nem todo usuário é MEI, e nem todo MEI tem o teto cheio
# ---------------------------------------------------------------------------

async def test_j8_painel_de_pf_nao_exibe_teto_do_mei(client):
    token = await _registrar(client)
    r = await client.patch(
        "/api/v1/perfil", headers=_h(token), json={"regime": "PF"}
    )
    assert r.status_code == 200, r.json()

    resumo = await _resumo(client, token)
    assert resumo["teto_anual"] is None


async def test_j9_teto_proporcional_no_ano_de_abertura(client):
    hoje = date.today()
    if hoje.month == 1:
        pytest.skip("em janeiro o teto proporcional coincide com o teto cheio")

    token = await _registrar(client)
    r = await client.patch(
        "/api/v1/perfil",
        headers=_h(token),
        json={"mes_abertura_mei": hoje.month, "ano_abertura_mei": hoje.year},
    )
    assert r.status_code == 200, r.json()

    meses_ativos = 12 - hoje.month + 1  # o mês de abertura conta
    esperado = Decimal("6750.00") * meses_ativos
    resumo = await _resumo(client, token)
    assert Decimal(resumo["teto_anual"]) == esperado


# ---------------------------------------------------------------------------
# A5 — mensagens e datas no formato de quem vai ler
# ---------------------------------------------------------------------------

async def test_j10_alerta_usa_moeda_em_formato_brasileiro(client):
    token = await _registrar(client)
    await _colar(client, token, "10/09 SERVICO PRESTADO CONSULTORIA ACME 50.000,00")

    r = await client.get("/api/v1/transacoes/alertas", headers=_h(token))
    mensagens = [a["mensagem"] for a in r.json()["itens"]]
    assert mensagens, "esperava o alerta de 60% do teto"
    assert "81000.00" not in mensagens[0], mensagens[0]
    assert "81.000,00" in mensagens[0], mensagens[0]


async def test_j11_colagem_sem_ano_nao_grava_data_no_futuro(client):
    hoje = date.today()
    futuro = hoje + timedelta(days=20)
    if futuro.year != hoje.year:
        pytest.skip("perto da virada do ano o caso não é reproduzível")

    token = await _registrar(client)
    r = await _colar(
        client, token, f"{futuro.day:02d}/{futuro.month:02d} SERVICO PRESTADO CLIENTE X 100,00"
    )
    assert r.status_code == 201, r.json()

    gravada = date.fromisoformat(r.json()["itens"][0]["data"])
    assert gravada <= hoje, gravada


async def test_j12_erro_de_arquivo_nao_expoe_estrutura_interna(client):
    token = await _registrar(client)
    csv = (
        "Extrato Conta Corrente\n"
        "Periodo;01/09/2026 a 30/09/2026\n"
        "\n"
        "Data Lançamento;Histórico;Descrição;Valor;Saldo\n"
        "01/09/2026;Pix recebido;FULANO;150,00;150,00\n"
    )
    r = await client.post(
        "/api/v1/transacoes/importar",
        headers=_h(token, idem=True),
        json={
            "formato": "csv",
            "conteudo_base64": base64.b64encode(csv.encode()).decode(),
        },
    )
    if r.status_code == 201:
        # Aceitar o arquivo também resolve: o preâmbulo foi ignorado.
        assert r.json()["importados"] == 1
        return
    mensagem = r.json()["mensagem"]
    assert "[" not in mensagem and "'" not in mensagem, mensagem


# ===========================================================================
# Fase 1 — aprender, corrigir, começar sem extrato, e servir todo o público
# ===========================================================================

JARGAO_PROIBIDO = ("Guardrail", "None", "§", "PF-PJ", "ponte", "heuristica")


async def _confirmar_com(client, token: str, tx_id: str, corpo: dict):
    return await client.patch(
        f"/api/v1/transacoes/{tx_id}/confirmar",
        headers=_h(token, idem=True),
        json=corpo,
    )


async def _corrigir(client, token: str, tx_id: str, corpo: dict):
    return await client.patch(
        f"/api/v1/transacoes/{tx_id}/corrigir",
        headers=_h(token, idem=True),
        json=corpo,
    )


async def _manual(client, token: str, corpo: dict):
    return await client.post(
        "/api/v1/transacoes/manual", headers=_h(token, idem=True), json=corpo
    )


async def _registrar_como(client, regime: str, email: str = "perfil@x.com") -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha12345", "cpf": CPF, "regime": regime},
    )
    assert r.status_code == 201, r.json()
    assert r.json()["user"]["regime"] == regime
    return r.json()["token"]


async def test_j13_ensinar_uma_vez_vale_para_os_iguais_e_para_os_proximos(client):
    token = await _registrar(client)
    await _colar(
        client,
        token,
        "02/09 PIX RECEBIDO CLINICA SORRISO LTDA 300,00\n"
        "09/09 PIX RECEBIDO CLINICA SORRISO LTDA 300,00\n"
        "16/09 PIX RECEBIDO CLINICA SORRISO LTDA 450,00\n"
        "17/09 PIX RECEBIDO PRIMO RICARDO 90,00",
    )
    fila = await _fila(client, token)
    assert len(fila) == 4
    alvo = next(i for i in fila if "CLINICA" in i["descricao_bruta"])

    r = await _confirmar_com(
        client, token, alvo["id"],
        {"categoria": "receita_servico", "proposito": "trabalho_servico", "lembrar": True},
    )
    assert r.status_code == 200, r.json()
    corpo = r.json()
    assert corpo["aplicadas_iguais"] == 2
    assert corpo["regra_criada"] is True
    assert Decimal(corpo["delta_total"]) == Decimal("1050.00")
    assert "mais 2 lançamentos iguais" in corpo["mensagem"]

    restantes = await _fila(client, token)
    assert [i["descricao_bruta"] for i in restantes] == ["PIX RECEBIDO PRIMO RICARDO"]
    assert Decimal((await _resumo(client, token))["faturamento_acumulado"]) == Decimal("1050.00")

    # No mês seguinte o mesmo pagador aparece de novo: não pergunta outra vez.
    await _colar(client, token, "01/10 PIX RECEBIDO CLINICA SORRISO LTDA 300,00")
    restantes = await _fila(client, token)
    assert all("CLINICA" not in i["descricao_bruta"] for i in restantes)
    assert Decimal((await _resumo(client, token))["faturamento_acumulado"]) == Decimal("1350.00")


async def test_j14_palpite_errado_tem_conserto(client):
    token = await _registrar(client)
    await _colar(client, token, "10/09 PAGAMENTO DE BOLETO CLARO S.A. -59,90")
    tx = (await _transacoes(client, token))[0]
    assert tx["needs_review"] is False  # a máquina classificou sozinha

    # o contrato antigo de /confirmar continua valendo (não está na fila)
    r = await _confirmar(client, token, tx["id"], "pessoal_prolabore")
    assert r.status_code == 409

    r = await _corrigir(
        client, token, tx["id"],
        {"categoria": "pessoal_prolabore", "proposito": "gasto_pessoal"},
    )
    assert r.status_code == 200, r.json()
    tx = (await _transacoes(client, token))[0]
    assert tx["rotulo"] == "Gasto pessoal ou da casa"
    assert tx["confirmada"] is True

    opiniao = await _opiniao(client, token, tx["id"])
    assert opiniao["grau_certeza_leitura"] == "fato_confirmado"
    assert "Você informou que foi gasto pessoal" in opiniao["fato"]


async def test_j15_corrigir_receita_confirmada_tira_do_faturamento(client):
    token = await _registrar(client)
    await _colar(client, token, "25/09 PIX RECEBIDO JOAO DA SILVA 100,00")
    item = (await _fila(client, token))[0]
    await _confirmar(client, token, item["id"], "receita_servico")
    assert Decimal((await _resumo(client, token))["faturamento_acumulado"]) == Decimal("100.00")

    r = await _corrigir(client, token, item["id"], {"categoria": "transferencia_propria"})
    assert r.status_code == 200, r.json()
    assert Decimal(r.json()["delta_faturamento"]) == Decimal("-100.00")
    assert Decimal((await _resumo(client, token))["faturamento_acumulado"]) == Decimal("0")


async def test_j16_da_para_comecar_sem_extrato(client):
    token = await _registrar(client)
    hoje = date.today().isoformat()

    r = await _manual(client, token, {
        "data": hoje, "descricao": "Corte de cabelo - cliente Ana",
        "valor": "50.00", "categoria": "receita_servico",
    })
    assert r.status_code == 201, r.json()
    assert r.json()["confirmada"] is True
    assert r.json()["origem"] == "manual"

    r = await _manual(client, token, {
        "data": hoje, "descricao": "Mercado da semana", "valor": "-120.00",
        "categoria": "pessoal_prolabore", "proposito": "gasto_pessoal",
    })
    assert r.status_code == 201, r.json()
    assert r.json()["rotulo"] == "Gasto pessoal ou da casa"

    r = await _manual(client, token, {"data": hoje, "descricao": "Recebi em dinheiro", "valor": "30.00"})
    assert r.status_code == 201, r.json()
    assert r.json()["needs_review"] is True  # sem dizer o que foi, vai para a revisão

    resumo = await _resumo(client, token)
    assert resumo["tem_transacoes"] is True
    assert resumo["total_lancamentos"] == 3
    assert resumo["pendentes_revisao"] == 1
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("50.00")
    assert Decimal(resumo["entradas_mes"]) == Decimal("80.00")
    assert Decimal(resumo["saidas_mes"]) == Decimal("120.00")

    amanha = (date.today() + timedelta(days=1)).isoformat()
    r = await _manual(client, token, {"data": amanha, "descricao": "x", "valor": "10.00"})
    assert r.status_code == 422
    r = await _manual(client, token, {"data": hoje, "descricao": "x", "valor": "0"})
    assert r.status_code == 422


async def test_j17_pessoa_fisica_nao_recebe_tratamento_de_mei(client):
    token = await _registrar_como(client, "PF")
    await _colar(
        client, token,
        "10/09 SERVICO PRESTADO REFORMA DONA LUCIA 60.000,00\n"
        "11/09 PIX RECEBIDO SEU ANTONIO OBRA 600,00",
    )
    item = (await _fila(client, token))[0]
    r = await _confirmar_com(
        client, token, item["id"],
        {"categoria": "receita_servico", "proposito": "trabalho_servico"},
    )
    assert "do que você recebeu por trabalho" in r.json()["mensagem"]

    resumo = await _resumo(client, token)
    assert resumo["regime"] == "PF"
    assert resumo["teto_anual"] is None
    assert resumo["percentual_consumido"] is None
    assert resumo["faixas"] == [] and resumo["proxima_faixa"] is None
    assert Decimal(resumo["faturamento_acumulado"]) == Decimal("60600.00")

    r = await client.get("/api/v1/transacoes/alertas", headers=_h(token))
    assert r.json()["itens"] == []  # nenhum alerta de limite do MEI para quem não é MEI

    opiniao = await _opiniao(client, token, item["id"])
    assert "CPF" in opiniao["interpretacao"]
    for campo in _TEXTOS_DO_PARECER:
        assert "MEI" not in opiniao[campo], (campo, opiniao[campo])


# --- Jornadas por perfil ----------------------------------------------------
# Extratos SINTÉTICOS. Cada linha traz a resposta que a pessoa daria (o id de
# uma das opções que a própria API oferece) ou None quando a descrição já é
# clara o bastante para o CaixaClaro ler sozinho.

PERFIS = {
    "manicure_mei": ("MEI", Decimal("290.00"), [
        ("02/09 PIX RECEBIDO JULIANA ALVES 45,00", "trabalho"),
        ("02/09 PIX RECEBIDO CARLA MENDES 80,00", "trabalho"),
        ("03/09 COMPRA NO DEBITO DISTRIBUIDORA BELEZA E CIA -132,40", "gasto_trabalho"),
        ("04/09 PIX RECEBIDO JULIANA ALVES NOVEMBRO 45,00", "trabalho"),
        ("05/09 PIX ENVIADO ALUGUEL SALA SALAO DA RUA 7 -400,00", "gasto_trabalho"),
        ("06/09 COMPRA NO DEBITO SUPERMERCADO BOM PRECO -210,15", "gasto_pessoal"),
        ("08/09 PIX RECEBIDO MAE 200,00", "doacao"),
        ("10/09 PAGAMENTO DAS MEI PGMEI -81,05", None),
        ("12/09 PIX RECEBIDO PATRICIA GOMES 120,00", "trabalho"),
        ("15/09 TARIFA MAQUININHA -9,90", None),
        ("20/09 PIX ENVIADO ESCOLA DO FILHO -350,00", "gasto_pessoal"),
    ]),
    "vendedora_marketplace_mei": ("MEI", Decimal("937.30"), [
        ("01/09 VENDA SHOPEE REPASSE 350,00", None),
        ("03/09 PIX RECEBIDO MERCADO PAGO REPASSE VENDAS 512,30", "venda"),
        ("04/09 PIX ENVIADO FORNECEDOR ATACADO CENTRAL -800,00", "gasto_trabalho"),
        ("05/09 COMPRA NO DEBITO CORREIOS POSTAGEM -64,20", "gasto_trabalho"),
        ("09/09 PIX RECEBIDO CLIENTE BALCAO ROSA 75,00", "venda"),
        ("10/09 PIX ENVIADO DEVOLUCAO CLIENTE ROSA -75,00", None),
        ("14/09 PIX RECEBIDO EMPRESTIMO DO IRMAO 1.000,00", None),
    ]),
    "pedreiro_autonomo_pf": ("PF", Decimal("1800.00"), [
        ("02/09 PIX RECEBIDO SEU ANTONIO OBRA 600,00", "trabalho"),
        ("03/09 COMPRA NO DEBITO CASA DO CONSTRUTOR -230,00", "gasto_trabalho"),
        ("05/09 PIX RECEBIDO DONA LUCIA REFORMA 1.200,00", "trabalho"),
        ("06/09 COMPRA NO DEBITO POSTO BR CENTRO -150,00", None),
        ("10/09 PIX ENVIADO ALUGUEL CASA -700,00", "gasto_pessoal"),
    ]),
    "assalariado_com_bico_pf": ("PF", Decimal("150.00"), [
        ("05/09 SALARIO MENSAL EMPRESA ABC 2.400,00", None),
        ("07/09 PIX RECEBIDO VIZINHO CONSERTO PORTAO 150,00", "trabalho"),
        ("08/09 COMPRA NO DEBITO SUPERMERCADO DA PRACA -320,00", "gasto_pessoal"),
        ("10/09 PIX ENVIADO MINHA CONTA POUPANCA -200,00", None),
    ]),
    "prestadora_simples": ("SIMPLES", Decimal("7300.00"), [
        ("03/09 TED RECEBIDA CONSULTORIA LTDA 4.500,00", None),
        ("12/09 PIX RECEBIDO ESCRITORIO MOURA E FILHOS 2.800,00", "trabalho"),
        ("15/09 PIX ENVIADO CONTADOR HONORARIOS -350,00", "gasto_trabalho"),
        ("20/09 TRANSF PRO LABORE TITULAR -3.000,00", "retirada"),
    ]),
}


@pytest.mark.parametrize("perfil", sorted(PERFIS))
async def test_j18_jornada_completa_por_perfil(client, perfil):
    regime, esperado, linhas = PERFIS[perfil]
    token = await _registrar_como(client, regime)
    r = await _colar(client, token, "\n".join(texto for texto, _ in linhas))
    assert r.status_code == 201, r.json()
    assert r.json()["importados"] == len(linhas)

    resposta_por_descricao = {}
    for texto, resposta in linhas:
        descricao = " ".join(texto.split(" ")[1:-1])
        resposta_por_descricao[descricao] = resposta

    # Nenhuma entrada de trabalho pode ter sido engolida em silêncio:
    # tudo o que a pessoa precisa responder está na fila.
    fila = await _fila(client, token)
    na_fila = {i["descricao_bruta"] for i in fila}
    esperadas_na_fila = {d for d, resp in resposta_por_descricao.items() if resp is not None}
    assert na_fila == esperadas_na_fila

    for item in fila:
        resposta = resposta_por_descricao[item["descricao_bruta"]]
        if resposta == "retirada":
            corpo = {"categoria": "pessoal_prolabore"}
        else:
            opcao = next(o for o in item["opcoes"] if o["id"] == resposta)
            corpo = {"categoria": opcao["categoria"], "proposito": opcao["proposito"]}
        r = await _confirmar_com(client, token, item["id"], corpo)
        assert r.status_code == 200, r.json()
        assert r.json()["mensagem"].startswith("Anotado:")

    assert await _fila(client, token) == []

    resumo = await _resumo(client, token)
    assert Decimal(resumo["faturamento_acumulado"]) == esperado
    assert (resumo["teto_anual"] is None) == (regime != "MEI")
    assert resumo["pendentes_revisao"] == 0

    for tx in await _transacoes(client, token):
        assert tx["rotulo"] and tx["rotulo"] != "Falta você dizer o que foi" or \
            tx["proposito"] in ("doacao_heranca",), tx
        opiniao = await _opiniao(client, token, tx["id"])
        esperado_selo = "fato_confirmado" if tx["confirmada"] else "leitura_provavel"
        assert opiniao["grau_certeza_leitura"] == esperado_selo, (tx, opiniao)
        direcao = "Saíram" if Decimal(tx["valor"]) < 0 else "Entraram"
        assert opiniao["fato"].startswith(direcao), opiniao["fato"]
        for campo in _TEXTOS_DO_PARECER:
            for termo in JARGAO_PROIBIDO:
                assert termo not in opiniao[campo], (termo, campo, opiniao[campo])
            if regime != "MEI":
                assert "MEI" not in opiniao[campo] or "DAS" in opiniao[campo], (campo, opiniao[campo])


async def test_j19_colagem_no_formato_que_o_app_do_banco_entrega(client):
    token = await _registrar(client)

    r = await _colar(
        client, token,
        "05/09/2026\nPIX RECEBIDO FULANO DE TAL\nR$ 150,00\n"
        "06/09/2026\nCOMPRA NO DEBITO PADARIA\n-R$ 18,50",
    )
    assert r.status_code == 201, r.json()
    itens = {i["descricao_bruta"]: i["valor"] for i in r.json()["itens"]}
    assert itens == {"PIX RECEBIDO FULANO DE TAL": "150.00", "COMPRA NO DEBITO PADARIA": "-18.50"}

    r = await _colar(client, token, "07/09/2026 PIX RECEBIDO BELTRANO 150.00")
    assert r.status_code == 201, r.json()
    assert r.json()["itens"][0]["valor"] == "150.00"

    csv = "data,descricao,valor\n2026-09-01,PIX RECEBIDO FULANO,150.00\n"
    r = await client.post(
        "/api/v1/transacoes/importar",
        headers=_h(token, idem=True),
        json={"formato": "csv", "conteudo_base64": base64.b64encode(csv.encode()).decode()},
    )
    assert r.status_code == 201, r.json()
    assert r.json()["itens"][0]["data"] == "2026-09-01"


async def test_j20_opcoes_de_resposta_vem_do_backend_e_respeitam_a_taxonomia(client):
    from caixaclaro.domain.fiscal.classificacao import PROPOSITOS_VALIDOS
    from caixaclaro.domain.fiscal.taxonomia import categoria_valida

    token = await _registrar(client)
    r = await client.get("/api/v1/transacoes/opcoes-resposta", headers=_h(token))
    assert r.status_code == 200, r.json()
    corpo = r.json()
    assert corpo["entrada"] and corpo["saida"]
    for opcao in corpo["entrada"] + corpo["saida"]:
        assert categoria_valida(opcao["categoria"]), opcao
        assert opcao["proposito"] in PROPOSITOS_VALIDOS, opcao
    # quem está começando precisa conseguir dizer "gasto pessoal"
    assert any(o["id"] == "gasto_pessoal" for o in corpo["saida"])
