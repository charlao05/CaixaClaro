"""Testes do webhook Asaas (M5.7)."""
import uuid

from caixaclaro.db import conexao


async def _registrar(client, email, cpf):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    async with conexao() as conn:
        uid = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
    return uid


async def _criar_payment(
    conn,
    user_id,
    *,
    status="pendente",
    asaas_id="pay_ext_1",
    external_ref=None,
    periodo_dias=30,
):
    if external_ref is None:
        external_ref = str(uuid.uuid4())
    row = await conn.fetchrow(
        """
        INSERT INTO payments
          (user_id, plano, valor, periodo_dias, status,
           asaas_payment_id, external_reference)
        VALUES ($1, 'pro_mensal', 49.90, $2, $3, $4, $5)
        RETURNING id
        """,
        user_id,
        periodo_dias,
        status,
        asaas_id,
        external_ref,
    )
    return row["id"], external_ref


async def _post_asaas(client, event, asaas_id, external_ref, event_id=None):
    if event_id is None:
        event_id = f"evt-{uuid.uuid4().hex[:8]}"
    return await client.post(
        "/api/v1/webhooks/asaas",
        json={
            "id": event_id,
            "event": event,
            "payment": {
                "id": asaas_id,
                "externalReference": external_ref,
            },
        },
    )


async def test_webhook_confirma_pendente_e_concede_periodo(client):
    uid = await _registrar(client, "wh1@x.com", "211.211.211-21")
    async with conexao() as conn:
        _, ref = await _criar_payment(conn, uid, status="pendente")

    r = await _post_asaas(client, "PAYMENT_CONFIRMED", "pay_ext_1", ref)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "confirmado"
    assert body["politica_b"] is False

    async with conexao() as conn:
        st = await conn.fetchval(
            "SELECT status FROM payments WHERE user_id = $1", uid
        )
        sub = await conn.fetchrow(
            "SELECT status, periodo_fim FROM subscriptions WHERE user_id = $1",
            uid,
        )
    assert st == "confirmado"
    assert sub is not None
    assert sub["status"] == "ativa"
    assert sub["periodo_fim"] is not None


async def test_webhook_politica_b_expirado_confirma(client):
    uid = await _registrar(client, "wh2@x.com", "212.212.212-22")
    async with conexao() as conn:
        _, ref = await _criar_payment(conn, uid, status="expirado")

    r = await _post_asaas(client, "PAYMENT_CONFIRMED", "pay_ext_1", ref)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "confirmado"
    assert body["politica_b"] is True

    async with conexao() as conn:
        sub = await conn.fetchrow(
            "SELECT status FROM subscriptions WHERE user_id = $1", uid
        )
    assert sub["status"] == "ativa"


async def test_webhook_idempotente_confirmado(client):
    uid = await _registrar(client, "wh3@x.com", "213.213.213-23")
    async with conexao() as conn:
        await _criar_payment(conn, uid, status="confirmado")
        await conn.execute(
            """
            INSERT INTO subscriptions
              (user_id, plano, status, periodo_inicio, periodo_fim)
            VALUES ($1, 'pro_mensal', 'ativa', now(), now() + interval '30 days')
            """,
            uid,
        )
        fim_antes = await conn.fetchval(
            "SELECT periodo_fim FROM subscriptions WHERE user_id = $1", uid
        )

    r = await _post_asaas(client, "PAYMENT_CONFIRMED", "pay_ext_1", str(uuid.uuid4()))
    assert r.status_code == 200
    async with conexao() as conn:
        fim_depois = await conn.fetchval(
            "SELECT periodo_fim FROM subscriptions WHERE user_id = $1", uid
        )
    assert fim_antes == fim_depois


async def test_webhook_duplo_lookup_por_asaas_id(client):
    uid = await _registrar(client, "wh4@x.com", "214.214.214-24")
    async with conexao() as conn:
        await _criar_payment(conn, uid, status="pendente", asaas_id="pay_lookup_1")

    r = await _post_asaas(client, "PAYMENT_CONFIRMED", "pay_lookup_1", None)
    assert r.status_code == 200
    assert r.json().get("status") == "confirmado"


async def test_webhook_duplo_lookup_por_external_ref(client):
    uid = await _registrar(client, "wh5@x.com", "215.215.215-25")
    async with conexao() as conn:
        _, ref = await _criar_payment(
            conn, uid, status="pendente", asaas_id=None, external_ref="ref-so"
        )

    r = await _post_asaas(client, "PAYMENT_CONFIRMED", "pay_id_novo", ref)
    assert r.status_code == 200
    async with conexao() as conn:
        st = await conn.fetchval(
            "SELECT status FROM payments WHERE user_id = $1", uid
        )
    assert st == "confirmado"


async def test_webhook_payment_nao_encontrado_retorna_ok(client):
    await _registrar(client, "wh6@x.com", "216.216.216-26")
    r = await _post_asaas(
        client, "PAYMENT_CONFIRMED", "pay_fantasma", "ref-fantasma"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["payment_encontrado"] is False


async def test_webhook_event_id_duplicado_nao_reprocessa(client):
    uid = await _registrar(client, "wh7@x.com", "217.217.217-27")
    async with conexao() as conn:
        await _criar_payment(conn, uid, status="pendente")

    payload = {
        "id": "evt-fixo-1",
        "event": "PAYMENT_CONFIRMED",
        "payment": {"id": "pay_ext_1", "externalReference": "x"},
    }
    r1 = await client.post("/api/v1/webhooks/asaas", json=payload)
    r2 = await client.post("/api/v1/webhooks/asaas", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json() == {"ok": True, "duplicado": True}


async def test_webhook_payload_invalido_400(client):
    r = await client.post(
        "/api/v1/webhooks/asaas",
        json={"event": "PAYMENT_CONFIRMED"},
    )
    assert r.status_code == 400
    assert r.json()["erro"] == "WEBHOOK_PAYLOAD_INVALIDO"


async def test_webhook_payment_overdue_marca_expirado(client):
    uid = await _registrar(client, "wh8@x.com", "218.218.218-28")
    async with conexao() as conn:
        _, ref = await _criar_payment(conn, uid, status="pendente")

    r = await _post_asaas(client, "PAYMENT_OVERDUE", "pay_ext_1", ref)
    assert r.status_code == 200
    assert r.json()["status"] == "expirado"

    async with conexao() as conn:
        st = await conn.fetchval(
            "SELECT status FROM payments WHERE user_id = $1", uid
        )
    assert st == "expirado"


async def test_webhook_payment_received_confirma(client):
    uid = await _registrar(client, "wh9@x.com", "219.219.219-29")
    async with conexao() as conn:
        _, ref = await _criar_payment(conn, uid, status="pendente")

    r = await _post_asaas(client, "PAYMENT_RECEIVED", "pay_ext_1", ref)
    assert r.status_code == 200
    assert r.json()["status"] == "confirmado"


async def test_webhook_confirma_pendente_reconciliacao(client):
    """pendente_reconciliacao + PAYMENT_CONFIRMED -> confirmado.

    Cenario do crash pos-POST que a reconciliacao do Asaas resolve.
    """
    uid = await _registrar(client, "wh10@x.com", "220.220.220-20")
    async with conexao() as conn:
        _, ref = await _criar_payment(conn, uid, status="pendente_reconciliacao")

    r = await _post_asaas(client, "PAYMENT_CONFIRMED", "pay_ext_1", ref)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["status"] == "confirmado"
    assert body["politica_b"] is False

    async with conexao() as conn:
        st = await conn.fetchval(
            "SELECT status FROM payments WHERE user_id = $1", uid
        )
        sub = await conn.fetchrow(
            "SELECT status FROM subscriptions WHERE user_id = $1", uid
        )
    assert st == "confirmado"
    assert sub is not None and sub["status"] == "ativa"


async def test_webhook_confirma_falhou(client):
    """falhou + PAYMENT_CONFIRMED -> confirmado.

    O Asaas diz que foi pago; nosso 'falhou' era erro interno.
    A verdade do dinheiro vem do provedor.
    """
    uid = await _registrar(client, "wh11@x.com", "221.221.221-21")
    async with conexao() as conn:
        _, ref = await _criar_payment(conn, uid, status="falhou")

    r = await _post_asaas(client, "PAYMENT_CONFIRMED", "pay_ext_1", ref)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["status"] == "confirmado"
    assert body["politica_b"] is False

    async with conexao() as conn:
        st = await conn.fetchval(
            "SELECT status FROM payments WHERE user_id = $1", uid
        )
        sub = await conn.fetchrow(
            "SELECT status FROM subscriptions WHERE user_id = $1", uid
        )
    assert st == "confirmado"
    assert sub is not None and sub["status"] == "ativa"


async def test_webhook_user_id_do_payload_e_ignorado(client):
    """Payload com user_id forjado NAO altera dono do payment.

    user_id vem SEMPRE do payment local. Se alguem um dia adicionar
    lookup de user_id no payload, este teste quebra.
    """
    uid_real = await _registrar(client, "forj1@x.com", "411.411.411-41")
    uid_forjado = await _registrar(client, "forj2@x.com", "412.412.412-42")

    async with conexao() as conn:
        _, ref = await _criar_payment(conn, uid_real, status="pendente")

    # Payload inclui user_id forjado, apontando para outro usuario
    r = await client.post(
        "/api/v1/webhooks/asaas",
        json={
            "id": f"evt-{uuid.uuid4().hex[:8]}",
            "event": "PAYMENT_CONFIRMED",
            "user_id": str(uid_forjado),
            "payment": {"id": "pay_ext_1", "externalReference": ref},
        },
    )
    assert r.status_code == 200, r.json()

    # Subscription so existe para o dono real (nao para o forjado)
    async with conexao() as conn:
        sub_real = await conn.fetchval(
            "SELECT count(*) FROM subscriptions WHERE user_id = $1", uid_real
        )
        sub_forjado = await conn.fetchval(
            "SELECT count(*) FROM subscriptions WHERE user_id = $1", uid_forjado
        )
    assert sub_real == 1
    assert sub_forjado == 0


async def test_webhook_politica_b_grava_audit(client):
    """Politica B precisa aparecer no audit_log com politica_b=True.

    Prova que a auditoria e efetivamente registrada, nao so o retorno.
    """
    uid = await _registrar(client, "audit-b@x.com", "413.413.413-43")
    async with conexao() as conn:
        _, ref = await _criar_payment(conn, uid, status="expirado")

    r = await _post_asaas(client, "PAYMENT_CONFIRMED", "pay_ext_1", ref)
    assert r.status_code == 200
    assert r.json()["politica_b"] is True

    async with conexao() as conn:
        row = await conn.fetchrow(
            """
            SELECT meta FROM audit_log
             WHERE user_id = $1
               AND acao = 'PAYMENT_CONFIRMED_APLICADO'
             ORDER BY id DESC LIMIT 1
            """,
            uid,
        )
    assert row is not None, "audit_log sem registro do PAYMENT_CONFIRMED"
    meta = row["meta"]
    if isinstance(meta, str):
        import json as _json
        meta = _json.loads(meta)
    assert meta["politica_b"] is True
    assert meta["status_anterior"] == "expirado"
    assert meta["status_novo"] == "confirmado"
