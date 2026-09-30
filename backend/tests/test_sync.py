"""Testes HTTP de sync — POST /contas/{id}/sync e GET /sync/{sync_id}."""
import uuid

from caixaclaro.db import conexao
from caixaclaro.services import pluggy as pluggy_mod


async def _registrar(client, email, cpf):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    token = r.json()["token"]
    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
    return token, str(user_id)


def _mockar_pluggy(monkeypatch, accounts):
    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return accounts

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)


async def _criar_conta(client, monkeypatch, email, cpf, acc_id, item_id):
    token, user_id = await _registrar(client, email, cpf)
    _mockar_pluggy(monkeypatch, [{"id": acc_id, "name": "Conta"}])
    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": f"evt-{item_id}",
            "itemId": item_id,
            "clientUserId": user_id,
        },
    )
    assert r.status_code == 200, r.json()
    async with conexao() as conn:
        account_id = await conn.fetchval(
            "SELECT id FROM accounts WHERE user_id = $1 AND provider_account_id = $2",
            uuid.UUID(user_id),
            acc_id,
        )
    return token, user_id, str(account_id)


async def test_iniciar_sync_cria_pendente(client, monkeypatch):
    token, user_id, account_id = await _criar_conta(
        client, monkeypatch, "sync1@x.com", "111.444.777-35", "acc-s1", "item-s1"
    )
    async with conexao() as conn:
        await conn.execute(
            "DELETE FROM sync_requests WHERE user_id = $1",
            uuid.UUID(user_id),
        )

    r = await client.post(
        f"/api/v1/contas/{account_id}/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 202, r.json()
    body = r.json()
    assert body["status"] == "pendente"
    assert "sync_id" in body


async def test_iniciar_sync_reusa_pendente_existente(client, monkeypatch):
    token, _, account_id = await _criar_conta(
        client, monkeypatch, "sync2@x.com", "222.222.220-60", "acc-s2", "item-s2"
    )
    headers = {"Authorization": f"Bearer {token}"}
    r1 = await client.post(f"/api/v1/contas/{account_id}/sync", headers=headers)
    r2 = await client.post(f"/api/v1/contas/{account_id}/sync", headers=headers)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["sync_id"] == r2.json()["sync_id"]


async def test_consultar_sync_200(client, monkeypatch):
    token, _, account_id = await _criar_conta(
        client, monkeypatch, "sync3@x.com", "333.333.330-90", "acc-s3", "item-s3"
    )
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post(f"/api/v1/contas/{account_id}/sync", headers=headers)
    sync_id = r.json()["sync_id"]

    r = await client.get(f"/api/v1/sync/{sync_id}", headers=headers)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["sync_id"] == sync_id
    assert body["status"] == "pendente"
    assert body["erro"] is None
    assert "criado_em" in body


async def test_consultar_sync_inexistente_404(client, monkeypatch):
    token, _, _ = await _criar_conta(
        client, monkeypatch, "sync4@x.com", "444.444.440-10", "acc-s4", "item-s4"
    )
    r = await client.get(
        f"/api/v1/sync/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert r.json()["erro"] == "SYNC_NAO_ENCONTRADO"


async def test_consultar_sync_de_outro_usuario_404(client, monkeypatch):
    token_a, _, account_a = await _criar_conta(
        client, monkeypatch, "sync5a@x.com", "555.555.550-40", "acc-s5", "item-s5"
    )
    r = await client.post(
        f"/api/v1/contas/{account_a}/sync",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    sync_id = r.json()["sync_id"]

    token_b, _, _ = await _criar_conta(
        client, monkeypatch, "sync5b@x.com", "556.556.556-16", "acc-s5b", "item-s5b"
    )
    r = await client.get(
        f"/api/v1/sync/{sync_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404


async def test_iniciar_sync_conta_inexistente_404(client, monkeypatch):
    token, _, _ = await _criar_conta(
        client, monkeypatch, "sync6@x.com", "666.666.660-70", "acc-s6", "item-s6"
    )
    r = await client.post(
        f"/api/v1/contas/{uuid.uuid4()}/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert r.json()["erro"] == "CONTA_NAO_ENCONTRADA"


async def test_iniciar_sync_conta_de_outro_usuario_404(client, monkeypatch):
    _, _, account_a = await _criar_conta(
        client, monkeypatch, "sync7a@x.com", "777.777.770-09", "acc-s7", "item-s7"
    )
    token_b, _, _ = await _criar_conta(
        client, monkeypatch, "sync7b@x.com", "778.778.778-38", "acc-s7b", "item-s7b"
    )
    r = await client.post(
        f"/api/v1/contas/{account_a}/sync",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404

async def test_worker_processa_sync_e_persiste_transacoes(client, monkeypatch):
    from caixaclaro.services import workers as workers_mod

    token, user_id, account_id = await _criar_conta(
        client,
        monkeypatch,
        "worker1@x.com",
        "111.444.777-35",
        "acc-worker-1",
        "item-worker-1",
    )

    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post(
        f"/api/v1/contas/{account_id}/sync",
        headers=headers,
    )
    assert r.status_code == 202, r.json()
    sync_id = r.json()["sync_id"]

    async def listar_transactions(account_id_provider, page=1, page_size=500):
        assert account_id_provider == "acc-worker-1"
        assert page == 1
        return {
            "results": [
                {
                    "id": "tx-worker-1",
                    "date": "2026-09-26",
                    "description": "Compra teste",
                    "amount": -42.50,
                },
                {
                    "id": "tx-worker-2",
                    "date": "2026-09-26",
                    "description": "Receita teste",
                    "amount": 150.00,
                },
            ],
            "total": 2,
            "page": 1,
            "totalPages": 1,
        }

    monkeypatch.setattr(
        workers_mod.pluggy,
        "listar_transactions",
        listar_transactions,
    )

    async with conexao() as conn:
        fez = await workers_mod.processar_um_sync(
            conn,
            "worker-test-1",
        )

        assert fez is True

        status = await conn.fetchval(
            "SELECT status FROM sync_requests WHERE id = $1",
            uuid.UUID(sync_id),
        )
        assert status == "completed"

        transacoes = await conn.fetch(
            """
            SELECT pluggy_tx_id, descricao_bruta, valor
              FROM transactions
             WHERE user_id = $1
             ORDER BY pluggy_tx_id
            """,
            uuid.UUID(user_id),
        )

    assert len(transacoes) == 2
    assert transacoes[0]["pluggy_tx_id"] == "tx-worker-1"
    assert transacoes[0]["descricao_bruta"] == "Compra teste"
    assert transacoes[0]["valor"] == -42.50
    assert transacoes[1]["pluggy_tx_id"] == "tx-worker-2"
    assert transacoes[1]["descricao_bruta"] == "Receita teste"
    assert transacoes[1]["valor"] == 150.00

async def test_worker_processa_sync_paginado(client, monkeypatch):
    from caixaclaro.services import workers as workers_mod

    token, user_id, account_id = await _criar_conta(
        client,
        monkeypatch,
        "worker2@x.com",
        "222.222.220-60",
        "acc-worker-2",
        "item-worker-2",
    )

    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post(
        f"/api/v1/contas/{account_id}/sync",
        headers=headers,
    )
    assert r.status_code == 202
    sync_id = r.json()["sync_id"]

    paginas = []

    async def listar_transactions(account_id_provider, page=1, page_size=500):
        paginas.append(page)
        assert account_id_provider == "acc-worker-2"
        if page == 1:
            return {
                "results": [
                    {
                        "id": "tx-page-1",
                        "date": "2026-09-26",
                        "description": "Pagina 1",
                        "amount": -10.00,
                    }
                ],
                "total": 2,
                "page": 1,
                "totalPages": 2,
            }
        return {
            "results": [
                {
                    "id": "tx-page-2",
                    "date": "2026-09-25",
                    "description": "Pagina 2",
                    "amount": 20.00,
                }
            ],
            "total": 2,
            "page": 2,
            "totalPages": 2,
        }

    monkeypatch.setattr(
        workers_mod.pluggy,
        "listar_transactions",
        listar_transactions,
    )

    async with conexao() as conn:
        fez = await workers_mod.processar_um_sync(
            conn,
            "worker-test-2",
        )

        assert fez is True

        status = await conn.fetchval(
            "SELECT status FROM sync_requests WHERE id = $1",
            uuid.UUID(sync_id),
        )
        assert status == "completed"

        quantidade = await conn.fetchval(
            "SELECT count(*) FROM transactions WHERE user_id = $1",
            uuid.UUID(user_id),
        )

    assert paginas == [1, 2]
    assert quantidade == 2


# ============================================================
# Worker M6 — claim, falha, recuperacao, idempotencia
# ============================================================

async def test_worker_claim_exclusao_mutua(client, monkeypatch):
    """Dois workers concorrentes: apenas um processa o sync.

    Prova FOR UPDATE SKIP LOCKED. Com um unico sync pendente,
    asyncio.gather dispara duas tasks; no maximo uma processa.
    """
    import asyncio
    from caixaclaro.services import workers as workers_mod

    token, user_id, account_id = await _criar_conta(
        client, monkeypatch, "worker-conc@x.com",
        "333.333.330-90", "acc-conc", "item-conc",
    )
    r = await client.post(
        f"/api/v1/contas/{account_id}/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 202

    chamadas = []

    async def listar_transactions(acc, page=1, page_size=500):
        chamadas.append(page)
        return {
            "results": [],
            "total": 0,
            "page": 1,
            "totalPages": 1,
        }

    monkeypatch.setattr(
        workers_mod.pluggy, "listar_transactions", listar_transactions
    )

    async def task(worker_id):
        async with conexao() as conn:
            return await workers_mod.processar_um_sync(conn, worker_id)

    resultados = await asyncio.gather(task("w-a"), task("w-b"))

    assert sum(resultados) == 1, f"esperava 1 processou, veio {resultados}"
    assert len(chamadas) == 1


async def test_worker_falha_pluggy_marca_failed(client, monkeypatch):
    """Excecao em pluggy.listar_transactions marca status='failed' com erro."""
    from caixaclaro.services import workers as workers_mod
    from fastapi import HTTPException

    token, user_id, account_id = await _criar_conta(
        client, monkeypatch, "worker-fail@x.com",
        "444.444.440-10", "acc-fail", "item-fail",
    )
    r = await client.post(
        f"/api/v1/contas/{account_id}/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    sync_id = r.json()["sync_id"]

    async def listar_transactions(acc, page=1, page_size=500):
        raise HTTPException(
            status_code=502,
            detail={"erro": "PLUGGY_TRANSACTIONS_FALHOU", "mensagem": "x"},
        )

    monkeypatch.setattr(
        workers_mod.pluggy, "listar_transactions", listar_transactions
    )

    async with conexao() as conn:
        fez = await workers_mod.processar_um_sync(conn, "w-fail")
        assert fez is True
        row = await conn.fetchrow(
            "SELECT status, erro FROM sync_requests WHERE id = $1",
            uuid.UUID(sync_id),
        )

    assert row["status"] == "failed"
    assert row["erro"] is not None
    assert "PLUGGY_TRANSACTIONS_FALHOU" in row["erro"]


async def test_worker_recupera_processando_antigo(client, monkeypatch):
    """Sync travado em 'processando' ha muito tempo volta para 'pendente'."""
    from caixaclaro.services import workers as workers_mod

    token, user_id, account_id = await _criar_conta(
        client, monkeypatch, "worker-rec@x.com",
        "555.555.550-40", "acc-rec", "item-rec",
    )

    async with conexao() as conn:
        await conn.execute(
            "DELETE FROM sync_requests WHERE user_id = $1",
            uuid.UUID(user_id),
        )
        await conn.execute(
            """
            INSERT INTO sync_requests
              (user_id, account_id, status, claimed_at, claimed_by)
            VALUES ($1, $2, 'processando',
                    now() - interval '10 minutes', 'worker-morto')
            """,
            uuid.UUID(user_id),
            uuid.UUID(account_id),
        )

        afetados = await workers_mod.recuperar_processando_antigos(
            conn, segundos=300
        )
        assert afetados == 1

        row = await conn.fetchrow(
            "SELECT status, claimed_by FROM sync_requests WHERE user_id = $1",
            uuid.UUID(user_id),
        )
    assert row["status"] == "pendente"
    assert row["claimed_by"] is None


async def test_worker_idempotente_nao_duplica_transactions(client, monkeypatch):
    """Rodar duas vezes com mesmos pluggy_tx_id nao duplica transactions."""
    from caixaclaro.services import workers as workers_mod

    token, user_id, account_id = await _criar_conta(
        client, monkeypatch, "worker-idem@x.com",
        "666.666.660-70", "acc-idem", "item-idem",
    )

    async def listar_transactions(acc, page=1, page_size=500):
        return {
            "results": [
                {
                    "id": "tx-idem-1",
                    "date": "2026-09-26",
                    "description": "A",
                    "amount": -10.00,
                },
                {
                    "id": "tx-idem-2",
                    "date": "2026-09-26",
                    "description": "B",
                    "amount": 20.00,
                },
            ],
            "total": 2,
            "page": 1,
            "totalPages": 1,
        }

    monkeypatch.setattr(
        workers_mod.pluggy, "listar_transactions", listar_transactions
    )

    # Primeira rodada: cria 2 sync e processa ambos
    r1 = await client.post(
        f"/api/v1/contas/{account_id}/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 202

    async with conexao() as conn:
        await workers_mod.processar_um_sync(conn, "w-i1")
        await workers_mod.processar_um_sync(conn, "w-i2")

        quantidade_1 = await conn.fetchval(
            "SELECT count(*) FROM transactions WHERE user_id = $1",
            uuid.UUID(user_id),
        )
        assert quantidade_1 == 2

    # Segunda rodada: novo sync, mesmos tx_ids
    r2 = await client.post(
        f"/api/v1/contas/{account_id}/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 202

    async with conexao() as conn:
        # Limpa o sync anterior para garantir que o novo é pego
        # (o POST reusa pendente; aqui não há pendente, então criou novo)
        await workers_mod.processar_um_sync(conn, "w-i3")

        quantidade_2 = await conn.fetchval(
            "SELECT count(*) FROM transactions WHERE user_id = $1",
            uuid.UUID(user_id),
        )

    # Continua 2 — idempotencia por (user_id, pluggy_tx_id)
    assert quantidade_2 == 2
