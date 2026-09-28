"""D5-A — propagacao de users.regime para ContextoClassificacao.

Nenhuma regra de classificacao consome ctx.regime hoje. Estes testes
garantem apenas que o dado real chega ao contexto, eliminando o default
silencioso "MEI" nos dois caminhos de classificacao (API e worker).
"""
import uuid

from caixaclaro.db import conexao
from caixaclaro.services import pluggy as pluggy_mod
from caixaclaro.services import workers as workers_mod
from caixaclaro.services.fiscal import processar_lancamento as real_pl


async def _registrar_com_regime(client, email, cpf, regime):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    token = r.json()["token"]
    r = await client.patch(
        "/api/v1/perfil",
        json={"regime": regime},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    async with conexao() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
    return token, str(user_id)


async def test_extrato_colar_propaga_regime(client, monkeypatch):
    """D5-A — POST /extrato/colar entrega users.regime ao contexto."""
    import caixaclaro.api.transacoes as t_mod

    capturados = []

    def spy(descricao, valor, *, contexto,
            cpf_titular_hash=None, cpf_contraparte_hash=None):
        capturados.append(contexto)
        return real_pl(
            descricao, valor,
            contexto=contexto,
            cpf_titular_hash=cpf_titular_hash,
            cpf_contraparte_hash=cpf_contraparte_hash,
        )

    monkeypatch.setattr(t_mod, "processar_lancamento", spy)

    token, _ = await _registrar_com_regime(
        client, "regime-col@x.com", "111.111.111-11", "PF"
    )
    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        json={"texto": "25/09 PIX RECEBIDO MARCOS R$ 650,00"},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 201, r.json()
    assert capturados, "processar_lancamento nao foi chamado"
    regimes = [c.regime for c in capturados]
    assert all(reg == "PF" for reg in regimes), regimes


async def test_reivindicar_sync_traz_regime_do_usuario(client, monkeypatch):
    """D5-A — a query de claim do worker carrega users.regime junto."""
    token, user_id = await _registrar_com_regime(
        client, "regime-worker@x.com", "222.222.222-22", "SIMPLES"
    )

    async def buscar_item(item_id):
        return {"id": item_id}

    async def listar_accounts(item_id):
        return [{"id": "acc-regime", "name": "Conta"}]

    monkeypatch.setattr(pluggy_mod, "buscar_item", buscar_item)
    monkeypatch.setattr(pluggy_mod, "listar_accounts", listar_accounts)

    r = await client.post(
        "/api/v1/webhooks/pluggy",
        json={
            "event": "item/created",
            "eventId": "evt-regime",
            "itemId": "item-regime",
            "clientUserId": user_id,
        },
    )
    assert r.status_code == 200, r.json()

    async with conexao() as conn:
        row = await workers_mod._reivindicar_sync(conn, "w-test-regime")

    assert row is not None, "nenhum sync pendente encontrado"
    assert row["regime"] == "SIMPLES", dict(row)
