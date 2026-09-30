import base64
import json
import time

from jose import jwt


def _b64(d: bytes) -> str:
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()


def _craft(header: dict, payload: dict, signature: bytes = b"") -> str:
    h = _b64(json.dumps(header, separators=(",", ":")).encode())
    p = _b64(json.dumps(payload, separators=(",", ":")).encode())
    s = _b64(signature)
    return f"{h}.{p}.{s}"


UUID_SUB = "00000000-0000-0000-0000-000000000000"
UUID_SID = "00000000-0000-0000-0000-000000000001"


async def test_token_alg_none_rejeitado(client):
    agora = int(time.time())
    token = _craft(
        {"alg": "none", "typ": "JWT"},
        {"sub": UUID_SUB, "sid": UUID_SID, "exp": agora + 60},
    )
    r = await client.get(
        "/api/v1/perfil", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_token_alg_rs256_forjado_rejeitado(client):
    agora = int(time.time())
    token = _craft(
        {"alg": "RS256", "typ": "JWT"},
        {"sub": UUID_SUB, "sid": UUID_SID, "exp": agora + 60},
        b"assinatura_falsa",
    )
    r = await client.get(
        "/api/v1/perfil", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_token_expirado_rejeitado(client):
    agora = int(time.time())
    token = jwt.encode(
        {"sub": UUID_SUB, "sid": UUID_SID, "exp": agora - 10},
        "x" * 48,
        algorithm="HS256",
    )
    r = await client.get(
        "/api/v1/perfil", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_token_assinatura_invalida_rejeitado(client):
    agora = int(time.time())
    token = jwt.encode(
        {"sub": UUID_SUB, "sid": UUID_SID, "exp": agora + 60},
        "outra_chave_completamente_diferente_de_48_bytes",
        algorithm="HS256",
    )
    r = await client.get(
        "/api/v1/perfil", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_token_sem_sid_rejeitado(client):
    agora = int(time.time())
    token = jwt.encode(
        {"sub": UUID_SUB, "exp": agora + 60},
        "x" * 48,
        algorithm="HS256",
    )
    r = await client.get(
        "/api/v1/perfil", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_token_sem_sub_rejeitado(client):
    agora = int(time.time())
    token = jwt.encode(
        {"sid": UUID_SID, "exp": agora + 60},
        "x" * 48,
        algorithm="HS256",
    )
    r = await client.get(
        "/api/v1/perfil", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_token_sid_nao_uuid_rejeitado_401_nao_500(client):
    agora = int(time.time())
    token = jwt.encode(
        {"sub": UUID_SUB, "sid": "nao-e-uuid", "exp": agora + 60},
        "x" * 48,
        algorithm="HS256",
    )
    r = await client.get(
        "/api/v1/perfil", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_senha_curta_rejeitada_com_422(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "curta@x.com", "senha": "1234567", "cpf": "111.444.777-35"},
    )
    assert r.status_code == 422
    assert r.json()["erro"] == "VALIDATION_ERROR"


async def test_senha_longa_rejeitada_com_422(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "longa@x.com", "senha": "a" * 73, "cpf": "111.444.777-35"},
    )
    assert r.status_code == 422
