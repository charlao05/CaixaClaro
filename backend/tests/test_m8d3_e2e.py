"""M8-D3 E2E — persistencia de proposito estendido + override em GET /opiniao."""
import uuid

from caixaclaro.db import conexao


def _key():
    return str(uuid.uuid4())


async def _registrar(client, email, cpf):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "senha": "senha123", "cpf": cpf},
    )
    assert r.status_code == 201, r.json()
    return r.json()["token"]


async def test_e2e_aporte_capital_persiste_e_override_parecer(client):
    """Circuito completo:
    colar -> classificar -> persistir proposito -> GET /opiniao -> override
    """
    token = await _registrar(
        client, "e2e-aporte@x.com", "123.456.789-09"
    )

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": "25/09 APORTE DE CAPITAL SOCIAL DO TITULAR R$ 5000,00"},
    )
    assert r.status_code == 201, r.json()

    async with conexao() as conn:
        row = await conn.fetchrow(
            "SELECT id, proposito FROM transactions "
            "WHERE descricao_bruta ILIKE '%APORTE DE CAPITAL%' "
            "ORDER BY criado_em DESC LIMIT 1"
        )
    assert row is not None, "tx nao persistida"
    assert row["proposito"] == "aporte_capital", dict(row)

    tx_id = str(row["id"])
    r = await client.get(
        f"/api/v1/transacoes/{tx_id}/opiniao",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    assert "aporte de capital" in body["fato"].lower()
    assert "capital social" in (
        body["interpretacao"] + body["possivel_tratamento_tributario"]
    ).lower()


async def test_e2e_dois_propositos_textos_diferentes(client):
    """Compara dois pareceres com proposito diferente: textos devem diferir."""
    token = await _registrar(
        client, "e2e-diff@x.com", "987.654.321-00"
    )

    r = await client.post(
        "/api/v1/transacoes/extrato/colar",
        headers={"Authorization": f"Bearer {token}",
                 "Idempotency-Key": _key()},
        json={"texto": (
            "25/09 APORTE DE CAPITAL SOCIAL DO TITULAR R$ 5000,00\n"
            "25/09 PIX RECEBIDO JOAO R$ 100,00"
        )},
    )
    assert r.status_code == 201, r.json()

    async with conexao() as conn:
        rows = await conn.fetch(
            "SELECT id, proposito FROM transactions "
            "WHERE descricao_bruta ILIKE '%APORTE DE CAPITAL%' "
            "   OR descricao_bruta ILIKE '%PIX RECEBIDO JOAO%'"
        )

    aporte = next(r for r in rows if r["proposito"] == "aporte_capital")
    pix = next(r for r in rows if r["proposito"] != "aporte_capital")

    async def _opiniao(tx_id):
        r = await client.get(
            f"/api/v1/transacoes/{tx_id}/opiniao",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.json()
        return r.json()

    o_aporte = await _opiniao(str(aporte["id"]))
    o_pix = await _opiniao(str(pix["id"]))

    assert o_aporte["fato"] != o_pix["fato"], (
        f"fatos iguais:\naporte={o_aporte['fato']!r}\npix={o_pix['fato']!r}"
    )
    assert o_aporte["possivel_tratamento_tributario"] != \
           o_pix["possivel_tratamento_tributario"]
