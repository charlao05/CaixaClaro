import json

from caixaclaro.db import conexao


def _texto_do_meta(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, dict):
        return json.dumps(valor)
    return str(valor)


async def test_perfil_nao_expoe_cpf(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "v1@x.com", "senha": "senha123", "cpf": "123.456.789-00"},
    )
    assert r.status_code == 201
    token = r.json()["token"]
    r = await client.get(
        "/api/v1/perfil", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    body = r.json()
    for chave in body:
        assert "cpf" not in chave.lower(), f"Chave vazada: {chave}"
    corpo_str = json.dumps(body)
    assert "12345678900" not in corpo_str
    assert "123.456.789-00" not in corpo_str


async def test_audit_login_falha_nao_expoe_cpf_nem_senha(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "v2@x.com", "senha": "senha123", "cpf": "987.654.321-00"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "v2@x.com", "senha": "errada_com_muita_informacao"},
    )
    async with conexao() as conn:
        rows = await conn.fetch(
            "SELECT meta, alvo FROM audit_log WHERE acao = 'login_falha'"
        )
    assert len(rows) == 1
    meta_str = _texto_do_meta(rows[0]["meta"])
    alvo_str = rows[0]["alvo"] or ""
    assert "98765432100" not in meta_str
    assert "987.654.321-00" not in meta_str
    assert "98765432100" not in alvo_str
    assert "errada_com_muita_informacao" not in meta_str
    assert "errada_com_muita_informacao" not in alvo_str
