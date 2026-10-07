"""Testes de services.senha — M12.

Cobre helpers puros (hash, geracao) e o ciclo com banco
(criar, consumir, expirado, ja usado, nova solicitacao invalida anterior).
"""
import uuid as _uuid

from caixaclaro.db import conexao
from caixaclaro.services import senha


def test_gerar_codigo_6_digitos_numericos():
    for _ in range(20):
        c = senha._gerar_codigo()
        assert len(c) == 6
        assert c.isdigit()


def test_gerar_codigo_zero_padded():
    vistos = {senha._gerar_codigo() for _ in range(50)}
    assert all(len(c) == 6 for c in vistos)


def test_hash_codigo_deterministico():
    assert senha._hash_codigo("123456") == senha._hash_codigo("123456")
    assert len(senha._hash_codigo("000000")) == 64


def test_hash_codigo_diferente_para_valores_diferentes():
    assert senha._hash_codigo("123456") != senha._hash_codigo("654321")


async def _criar_user(conn) -> str:
    uid = _uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, email, senha_hash, cpf_hash, cpf_cifrado, regime) "
        "VALUES ($1, $2, $3, $4, $5, 'MEI')",
        uid,
        f"reset_{uid.hex[:8]}@x.com",
        "$2b$12$" + "x" * 53,
        f"hash_{uid.hex}",
        b"\x00" * 32,
    )
    return str(uid)


async def test_criar_e_consumir_codigo(client):
    async with conexao() as conn:
        uid = await _criar_user(conn)
        raw = await senha.criar_solicitacao(conn, uid)
        assert len(raw) == 6 and raw.isdigit()
        assert await senha.consumir_codigo(conn, uid, raw) is True


async def test_codigo_ja_usado_retorna_false(client):
    async with conexao() as conn:
        uid = await _criar_user(conn)
        raw = await senha.criar_solicitacao(conn, uid)
        assert await senha.consumir_codigo(conn, uid, raw) is True
        assert await senha.consumir_codigo(conn, uid, raw) is False


async def test_codigo_invalido_retorna_false(client):
    async with conexao() as conn:
        uid = await _criar_user(conn)
        assert await senha.consumir_codigo(conn, uid, "000000") is False
        assert await senha.consumir_codigo(conn, uid, "") is False
        assert await senha.consumir_codigo(conn, uid, "12345") is False
        assert await senha.consumir_codigo(conn, uid, "1234567") is False


async def test_codigo_expirado_retorna_false(client):
    async with conexao() as conn:
        uid = await _criar_user(conn)
        raw = "000123"
        h = senha._hash_codigo(raw)
        await conn.execute(
            "INSERT INTO password_reset_tokens (user_id, codigo_hash, expira_em) "
            "VALUES ($1, $2, now() - interval '1 minute')",
            _uuid.UUID(uid),
            h,
        )
        assert await senha.consumir_codigo(conn, uid, raw) is False


async def test_nova_solicitacao_invalida_anterior(client):
    async with conexao() as conn:
        uid = await _criar_user(conn)
        primeira = await senha.criar_solicitacao(conn, uid)
        segunda = await senha.criar_solicitacao(conn, uid)
        assert await senha.consumir_codigo(conn, uid, primeira) is False
        assert await senha.consumir_codigo(conn, uid, segunda) is True


async def test_codigo_de_outro_usuario_nao_consome(client):
    async with conexao() as conn:
        a = await _criar_user(conn)
        b = await _criar_user(conn)
        raw_a = await senha.criar_solicitacao(conn, a)
        assert await senha.consumir_codigo(conn, b, raw_a) is False
        assert await senha.consumir_codigo(conn, a, raw_a) is True