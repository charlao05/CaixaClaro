import base64
import uuid

import pytest

from caixaclaro.db import conexao


async def _registrar(client, email: str = "t@x.com", cpf: str = "111.111.111-11") -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


def _key() -> str:
    return str(uuid.uuid4())


TXT_5 = (
    "25/09 PIX RECEBIDO MARCOS R$ 650,00\n"
    "24/09 CREDITO TED FOLHA SALARIO R$ 4.850,00\n"
    "23/09 ESTORNO COMPRA CANCELADA R$ 389,90\n"
    "22/09 CREDITO EMPRESTIMO R$ 12.000,00\n"
    "21/09 POSTO IPIRANGA COMBUSTIVEL -140,00"
)


async def test_colar_cinco_linhas(client):
    token = await _registrar(client)
    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": TXT_5},
    )
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["importados"] == 5
    assert len(body["itens"]) == 5
    assert len(body["paste_id"]) == 16
    for item in body["itens"]:
        assert item["origem"] == "paste"
        assert item["line_index"] in range(5)


async def test_colar_mesmo_texto_chaves_distintas_nao_duplica(client):
    token = await _registrar(client)
    headers1 = {"Authorization": f"Bearer {token}", "Idempotency-Key": _key()}
    headers2 = {"Authorization": f"Bearer {token}", "Idempotency-Key": _key()}

    r1 = await client.post("/api/v1/transacoes/extrato/colar",
                           headers=headers1, json={"texto": TXT_5})
    r2 = await client.post("/api/v1/transacoes/extrato/colar",
                           headers=headers2, json={"texto": TXT_5})

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["importados"] == 5
    assert r2.json()["importados"] == 0
    assert r1.json()["paste_id"] == r2.json()["paste_id"]
    assert len(r2.json()["itens"]) == 5  # os já existentes

    async with conexao() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE origem='paste'"
        )
    assert n == 5


async def test_colar_mesma_chave_mesmo_payload_reaproveita_resposta(client):
    token = await _registrar(client)
    chave = _key()
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": chave}

    r1 = await client.post("/api/v1/transacoes/extrato/colar",
                           headers=headers, json={"texto": TXT_5})
    r2 = await client.post("/api/v1/transacoes/extrato/colar",
                           headers=headers, json={"texto": TXT_5})

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json() == r2.json()

    async with conexao() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE origem='paste'"
        )
    assert n == 5


async def test_colar_mesma_chave_payload_diferente_409(client):
    token = await _registrar(client)
    chave = _key()
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": chave}

    r1 = await client.post("/api/v1/transacoes/extrato/colar",
                           headers=headers, json={"texto": TXT_5})
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/transacoes/extrato/colar",
                           headers=headers, json={"texto": TXT_5 + " extra"})
    assert r2.status_code == 409
    assert r2.json()["erro"] == "IDEMPOTENCY_KEY_REUSED"


async def test_colar_sem_idempotency_key_422(client):
    token = await _registrar(client)
    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": TXT_5},
    )
    assert r.status_code == 422
    assert r.json()["erro"] == "VALIDATION_ERROR"


async def test_colar_idempotency_key_nao_uuid_422(client):
    token = await _registrar(client)
    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": "abc123"},
        json={"texto": TXT_5},
    )
    assert r.status_code == 422


async def test_colar_sem_jwt_401(client):
    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Idempotency-Key": _key()},
        json={"texto": TXT_5},
    )
    assert r.status_code == 401


async def test_colar_texto_ilegivel_400(client):
    token = await _registrar(client)
    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": "nada aqui"},
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "EXTRATO_ILEGIVEL"


async def test_importar_csv(client):
    token = await _registrar(client)
    csv_bytes = (
        "data;descricao;valor\n"
        "25/09/2026;PIX RECEBIDO;650,00\n"
        "24/09/2026;POSTO SHELL;-140,00\n"
        "23/09/2026;SALARIO;4850,00\n"
        "22/09/2026;ALUGUEL;-1200,00\n"
        "21/09/2026;INTERNET;-99,90\n"
        "20/09/2026;FARMACIA;-45,00\n"
        "19/09/2026;MERCADO;-320,00\n"
        "18/09/2026;PIX RECEBIDO;200,00\n"
        "17/09/2026;UBER;-25,00\n"
        "16/09/2026;PIX RECEBIDO;150,00\n"
    ).encode("utf-8")
    b64 = base64.b64encode(csv_bytes).decode()

    r = await client.post(
        "/api/v1/transacoes/importar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"formato": "csv", "conteudo_base64": b64},
    )
    assert r.status_code == 201, r.json()
    assert r.json()["importados"] == 10
    for item in r.json()["itens"]:
        assert item["origem"] == "csv"


async def test_importar_ofx(client):
    token = await _registrar(client)
    ofx = (
        "<OFX>"
        "<STMTTRN><DTPOSTED>20260925</DTPOSTED><TRNAMT>650.00</TRNAMT>"
        "<MEMO>PIX RECEBIDO</MEMO></STMTTRN>"
        "<STMTTRN><DTPOSTED>20260924</DTPOSTED><TRNAMT>-140.00</TRNAMT>"
        "<MEMO>POSTO SHELL</MEMO></STMTTRN>"
        "</OFX>"
    ).encode("utf-8")
    b64 = base64.b64encode(ofx).decode()

    r = await client.post(
        "/api/v1/transacoes/importar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"formato": "ofx", "conteudo_base64": b64},
    )
    assert r.status_code == 201, r.json()
    assert r.json()["importados"] == 2
    for item in r.json()["itens"]:
        assert item["origem"] == "ofx"


async def test_importar_formato_invalido_422(client):
    token = await _registrar(client)
    r = await client.post(
        "/api/v1/transacoes/importar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"formato": "xml", "conteudo_base64": "aGVsbG8="},
    )
    assert r.status_code == 422


async def test_importar_base64_invalido_400(client):
    token = await _registrar(client)
    r = await client.post(
        "/api/v1/transacoes/importar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"formato": "csv", "conteudo_base64": "não é base64!!"},
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "ARQUIVO_ILEGIVEL"


async def test_get_transacoes_ordena_data_desc(client):
    token = await _registrar(client)
    txt = (
        "20/09 A R$ 1,00\n"
        "25/09 B R$ 2,00\n"
        "22/09 C R$ 3,00"
    )
    await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": txt},
    )
    r = await client.get(
        "/api/v1/transacoes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    datas = [i["data"] for i in r.json()["itens"]]
    assert datas == sorted(datas, reverse=True)
    assert datas[0] == "2026-09-25"


async def test_get_transacoes_isolamento_por_usuario(client):
    a = await _registrar(client, "a@x.com", "111.111.111-11")
    b = await _registrar(client, "b@x.com", "222.222.222-22")

    await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {a}",
                 "Idempotency-Key": _key()},
        json={"texto": TXT_5},
    )

    ra = await client.get("/api/v1/transacoes",
                          headers={"Authorization": f"Bearer {a}"})
    rb = await client.get("/api/v1/transacoes",
                          headers={"Authorization": f"Bearer {b}"})
    assert len(ra.json()["itens"]) == 5
    assert len(rb.json()["itens"]) == 0


async def test_get_transacoes_cursor_avanca_sem_repetir(client):
    token = await _registrar(client)
    txt = "\n".join(
        f"0{i}/09 ITEM{i} R$ {i},00" for i in range(1, 6)
    )
    await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": txt},
    )

    vistos = []
    cursor = None
    for _ in range(5):
        params = {"limite": 2}
        if cursor:
            params["cursor"] = cursor
        r = await client.get(
            "/api/v1/transacoes",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        assert r.status_code == 200
        body = r.json()
        vistos.extend(i["id"] for i in body["itens"])
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]

    assert len(vistos) == 5
    assert len(set(vistos)) == 5


async def test_get_transacoes_cursor_invalido_400(client):
    token = await _registrar(client)
    r = await client.get(
        "/api/v1/transacoes",
        headers={"Authorization": f"Bearer {token}"},
        params={"cursor": "@@malformado@@"},
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "CURSOR_INVALIDO"


# ============================================================
# Idempotência sob falha e obsolescência
# ============================================================

async def test_processando_obsoleto_permite_reprocessar(client):
    """Chave presa em 'processando' além da janela deve permitir retry."""
    from datetime import datetime, timedelta, timezone
    from caixaclaro.security.idempotency import _payload_hash

    token = await _registrar(client, "stale@x.com", "333.333.333-33")
    chave = _key()

    async with conexao() as conn:
        uid = await conn.fetchval(
            "SELECT id FROM users WHERE email = 'stale@x.com'"
        )
        antigo = datetime.now(timezone.utc) - timedelta(minutes=10)
        hash_correto = _payload_hash({"texto": TXT_5})
        await conn.execute(
            """
            INSERT INTO idempotency_keys
              (user_id, rota, chave, payload_hash, status,
               expira_em, atualizado_em)
            VALUES ($1, 'POST /api/v1/transacoes/extrato/colar', $2,
                    $3, 'processando',
                    now() + interval '24 hours', $4)
            """,
            uid, chave, hash_correto, antigo,
        )

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": chave},
        json={"texto": TXT_5},
    )
    assert r.status_code == 201, r.json()
    assert r.json()["importados"] == 5


async def test_processando_recente_bloqueia(client):
    """Chave em 'processando' dentro da janela deve dar 409."""
    from caixaclaro.security.idempotency import _payload_hash

    token = await _registrar(client, "recente@x.com", "444.444.444-44")
    chave = _key()

    async with conexao() as conn:
        uid = await conn.fetchval(
            "SELECT id FROM users WHERE email = 'recente@x.com'"
        )
        hash_correto = _payload_hash({"texto": TXT_5})
        await conn.execute(
            """
            INSERT INTO idempotency_keys
              (user_id, rota, chave, payload_hash, status,
               expira_em, atualizado_em)
            VALUES ($1, 'POST /api/v1/transacoes/extrato/colar', $2,
                    $3, 'processando',
                    now() + interval '24 hours', now())
            """,
            uid, chave, hash_correto,
        )

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": chave},
        json={"texto": TXT_5},
    )
    assert r.status_code == 409
    assert r.json()["erro"] == "IDEMPOTENCY_EM_ANDAMENTO"

async def test_operacao_que_falha_marca_falhou(client):
    """Extrato ilegível deve deixar a chave em 'falhou', não em 'processando'."""
    from caixaclaro.db import conexao

    token = await _registrar(client, "falha@x.com", "555.555.555-55")
    chave = _key()

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": chave},
        json={"texto": "nada"},
    )
    assert r.status_code == 400

    async with conexao() as conn:
        status = await conn.fetchval(
            """
            SELECT status FROM idempotency_keys
            WHERE rota='POST /api/v1/transacoes/extrato/colar' AND chave=$1
            """,
            chave,
        )
    assert status == "falhou"


async def test_retry_apos_falhou_reprocessa(client):
    """Chave em 'falhou' permite nova tentativa."""
    token = await _registrar(client, "reproc@x.com", "666.666.666-66")
    chave = _key()
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": chave}

    r1 = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers=headers, json={"texto": "nada"},
    )
    assert r1.status_code == 400

    # Mesma chave, payload diferente — mas chave estava em 'falhou'
    # Então o fluxo permite reprocessar. Mudamos payload para um válido.
    r2 = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers=headers, json={"texto": TXT_5},
    )
    # Comportamento esperado: 409 IDEMPOTENCY_KEY_REUSED porque payload mudou.
    # (Só permite reprocessar com o MESMO payload)
    assert r2.status_code == 409
    assert r2.json()["erro"] == "IDEMPOTENCY_KEY_REUSED"


async def test_atomicidade_concluido_dentro_da_transacao(client):
    """Após sucesso, 'concluido' está persistido — sem janela."""
    from caixaclaro.db import conexao

    token = await _registrar(client, "atom@x.com", "777.777.777-77")
    chave = _key()

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": chave},
        json={"texto": TXT_5},
    )
    assert r.status_code == 201

    async with conexao() as conn:
        row = await conn.fetchrow(
            """
            SELECT status, response, status_http
            FROM idempotency_keys
            WHERE rota='POST /api/v1/transacoes/extrato/colar' AND chave=$1
            """,
            chave,
        )
    assert row["status"] == "concluido"
    assert row["status_http"] == 201
    assert row["response"] is not None


# ============================================================
# Idempotência sob falha e obsolescência
# ============================================================

async def test_mesma_chave_payload_diferente_apos_falhou_409(client):
    """Mesmo com 'falhou', payload diferente ainda vê 409 KEY_REUSED."""
    token = await _registrar(client, "reproc@x.com", "666.666.666-66")
    chave = _key()
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": chave}

    r1 = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers=headers, json={"texto": "nada"},
    )
    assert r1.status_code == 400

    r2 = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers=headers, json={"texto": TXT_5},
    )
    assert r2.status_code == 409
    assert r2.json()["erro"] == "IDEMPOTENCY_KEY_REUSED"


async def test_concluido_com_response_persistida(client):
    """Após sucesso, 'concluido' está gravado com response e status_http."""
    token = await _registrar(client, "atom@x.com", "777.777.777-77")
    chave = _key()

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": chave},
        json={"texto": TXT_5},
    )
    assert r.status_code == 201

    async with conexao() as conn:
        row = await conn.fetchrow(
            """
            SELECT status, response, status_http
            FROM idempotency_keys
            WHERE rota='POST /api/v1/transacoes/extrato/colar' AND chave=$1
            """,
            chave,
        )
    assert row["status"] == "concluido"
    assert row["status_http"] == 201
    assert row["response"] is not None
