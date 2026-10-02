"""Testes do migrator — M10a."""
import uuid

import asyncpg
import pytest

from caixaclaro import migration_runner


@pytest.fixture
async def schema_isolado():
    """Cria um schema PostgreSQL dedicado por teste e o remove no fim."""
    from caixaclaro.config import settings

    nome = f"mtest_{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(settings().database_url)
    await conn.execute(f'CREATE SCHEMA "{nome}"')
    await conn.execute(f'SET search_path = "{nome}", public')
    try:
        yield conn
    finally:
        await conn.execute(f'DROP SCHEMA "{nome}" CASCADE')
        await conn.close()


async def test_aplica_migrations_em_banco_vazio(schema_isolado, tmp_path):
    (tmp_path / "001_a.sql").write_text(
        "CREATE TABLE t_a (id INT PRIMARY KEY);", encoding="utf-8"
    )
    (tmp_path / "002_b.sql").write_text(
        "CREATE TABLE t_b (id INT PRIMARY KEY);", encoding="utf-8"
    )

    n = await migration_runner.aplicar(
        schema_isolado, migrations_dir=tmp_path
    )
    assert n == 2

    registradas = await schema_isolado.fetch(
        "SELECT filename FROM schema_migrations ORDER BY filename"
    )
    assert [r["filename"] for r in registradas] == ["001_a.sql", "002_b.sql"]


async def test_segunda_execucao_pula_tudo(schema_isolado, tmp_path):
    (tmp_path / "001_a.sql").write_text(
        "CREATE TABLE t_a (id INT PRIMARY KEY);", encoding="utf-8"
    )

    n1 = await migration_runner.aplicar(
        schema_isolado, migrations_dir=tmp_path
    )
    n2 = await migration_runner.aplicar(
        schema_isolado, migrations_dir=tmp_path
    )

    assert n1 == 1
    assert n2 == 0


async def test_sha_divergente_falha(schema_isolado, tmp_path):
    arq = tmp_path / "001_a.sql"
    arq.write_text("CREATE TABLE t_a (id INT PRIMARY KEY);", encoding="utf-8")
    await migration_runner.aplicar(schema_isolado, migrations_dir=tmp_path)

    # Altera o conteudo — simulando migration reescrita pos-aplicacao
    arq.write_text(
        "CREATE TABLE t_a (id INT PRIMARY KEY, extra TEXT);",
        encoding="utf-8",
    )

    with pytest.raises(
        migration_runner.MigrationError, match="SHA-256 diferente"
    ):
        await migration_runner.aplicar(schema_isolado, migrations_dir=tmp_path)


async def test_migration_que_falha_nao_registra(schema_isolado, tmp_path):
    (tmp_path / "001_bad.sql").write_text(
        "CREATE TABLE t_x (id INT); ESTE NAO E SQL VALIDO;",
        encoding="utf-8",
    )

    with pytest.raises(asyncpg.PostgresError):
        await migration_runner.aplicar(
            schema_isolado, migrations_dir=tmp_path
        )

    registradas = await schema_isolado.fetch(
        "SELECT filename FROM schema_migrations"
    )
    assert registradas == []

    existe = await schema_isolado.fetchval(
        "SELECT to_regclass('t_x') IS NOT NULL"
    )
    assert existe is False


async def test_aplica_migrations_reais(schema_isolado):
    n = await migration_runner.aplicar(schema_isolado)
    assert n == 10

    existe_users = await schema_isolado.fetchval(
        "SELECT to_regclass('users') IS NOT NULL"
    )
    assert existe_users is True


async def test_env_var_migrations_dir(monkeypatch, tmp_path):
    """MIGRATIONS_DIR tem precedencia sobre o caminho relativo ao arquivo."""
    (tmp_path / "001_x.sql").write_text(
        "CREATE TABLE t_x_env (id INT);", encoding="utf-8"
    )

    monkeypatch.setenv("MIGRATIONS_DIR", str(tmp_path))
    caminho = migration_runner._migrations_dir_padrao()

    assert caminho == tmp_path
