"""Teste de integracao HTTP do gate E1.

Prova, via HTTP real (nao chamando usuario_ativo direto), que:

- usuario com trial vigente passa nas rotas de produto;
- usuario com trial expirado recebe 402 nas rotas de produto;
- o mesmo usuario com trial expirado continua acessando perfil e billing;
- revogar conta continua acessivel (excecao de privacidade, decisao de produto).

O fixture 'limpar_estado' do conftest apaga 'users' entre testes, entao
reusar CPF e' seguro.
"""
import uuid
from datetime import datetime, timedelta, timezone

from caixaclaro.db import conexao


CPF_FIXO = "52998224725"


async def _registrar(client, email):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha_segura_123", "cpf": CPF_FIXO},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _envelhecer(user_id, dias):
    async with conexao() as conn:
        await conn.execute(
            "UPDATE users SET criado_em = now() - ($2 || ' days')::interval "
            "WHERE id = $1",
            uuid.UUID(user_id),
            str(dias),
        )


def _hdr(token):
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": str(uuid.uuid4()),
    }


async def test_trial_vigente_passa_em_produto(client):
    dados = await _registrar(client, "vigente_e1@example.com")
    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        json={"texto": "01/01/2026 PIX RECEBIDO JOAO 100,00"},
        headers=_hdr(dados["token"]),
    )
    assert r.status_code == 201, r.text


async def test_trial_expirado_402_em_produto(client):
    dados = await _registrar(client, "expirado_e1@example.com")
    await _envelhecer(dados["user"]["id"], dias=30)

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        json={"texto": "01/01/2026 PIX RECEBIDO JOAO 100,00"},
        headers=_hdr(dados["token"]),
    )
    assert r.status_code == 402, r.text
    body = r.json()
    assert body["erro"] == "ACESSO_BLOQUEADO"
    assert body["estado"] == "trial_expirado"


async def test_trial_expirado_libera_perfil_e_billing(client):
    """Perfil e billing NAO sao gate: precisam continuar funcionando."""
    dados = await _registrar(client, "exp_perfil_e1@example.com")
    await _envelhecer(dados["user"]["id"], dias=30)
    h = {"Authorization": f"Bearer {dados['token']}"}

    r_perfil = await client.get("/api/v1/perfil", headers=h)
    assert r_perfil.status_code == 200, r_perfil.text

    r_billing = await client.get("/api/v1/billing/status", headers=h)
    assert r_billing.status_code == 200, r_billing.text


async def test_trial_expirado_permite_revogar_conta(client):
    """revogar nao e gate: precisa continuar funcionando (decisao de produto).

    Conta inexistente: o esperado e' 404 da logica de negocio,
    NAO 402 do gate. Se vier 402, revogar entrou no gate por engano.
    """
    dados = await _registrar(client, "exp_revogar_e1@example.com")
    await _envelhecer(dados["user"]["id"], dias=30)
    h = {"Authorization": f"Bearer {dados['token']}"}

    r = await client.post(
        "/api/v1/contas/00000000-0000-0000-0000-000000000000/revogar",
        headers=h,
    )
    assert r.status_code != 402, f"revogar foi bloqueado por engano: {r.text}"
    assert r.status_code == 404, r.text

async def _criar_subscription(user_id, *, periodo_fim):
    async with conexao() as conn:
        await conn.execute(
            "INSERT INTO subscriptions (user_id, plano, status, periodo_fim) "
            "VALUES ($1, 'mensal', 'ativa', $2)",
            uuid.UUID(user_id),
            periodo_fim,
        )


async def test_assinatura_vencida_402_com_estado_assinatura_expirada(client):
    """E2: motivo chega ao HTTP quando ha subscription vencida."""
    dados = await _registrar(client, "assin_venc_e1@example.com")
    await _envelhecer(dados["user"]["id"], dias=30)
    await _criar_subscription(
        dados["user"]["id"],
        periodo_fim=datetime.now(timezone.utc) - timedelta(days=1),
    )

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        json={"texto": "01/01/2026 PIX RECEBIDO JOAO 100,00"},
        headers=_hdr(dados["token"]),
    )
    assert r.status_code == 402, r.text
    body = r.json()
    assert body["erro"] == "ACESSO_BLOQUEADO"
    assert body["estado"] == "assinatura_expirada"