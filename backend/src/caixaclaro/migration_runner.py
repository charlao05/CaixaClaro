"""Migrator de produção — M10a.

Aplica migrations/*.sql em ordem alfabética, rastreando cada uma em
schema_migrations com filename + sha256.

Diferenças em relação a backend/tests/conftest.py:
- conftest é tolerante a reexecução (engole Duplicate*Error)
- migration_runner é estrito: sabe exatamente o que foi aplicado
  e falha se o conteúdo de uma migration já registrada mudou
"""
import asyncio
import hashlib
import os
import sys
from pathlib import Path

import asyncpg

from .config import settings

# Chave arbitrária para o advisory lock. Qualquer valor int64 cabe.
ADVISORY_LOCK_KEY = 0x4341495841  # "CAIXA" em hex


CREATE_SCHEMA_MIGRATIONS = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    sha256     TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class MigrationError(Exception):
    """Uma migration nao pode ser aplicada com seguranca."""


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _migrations_dir_padrao() -> Path:
    """Diretorio das migrations.

    Ordem de resolucao:
    1. Variavel de ambiente MIGRATIONS_DIR (usada em producao, onde o
       pacote esta instalado em site-packages e o caminho relativo ao
       arquivo nao aponta para o repo).
    2. Caminho relativo ao arquivo — funciona em editable install,
       que e' como dev e CI operam.
    """
    env = os.environ.get("MIGRATIONS_DIR")
    if env:
        return Path(env)
    # <repo>/backend/migrations — sobe de src/caixaclaro/ ate backend/
    return Path(__file__).resolve().parents[2] / "migrations"


async def aplicar(
    conn: asyncpg.Connection, migrations_dir: Path | None = None
) -> int:
    """Aplica migrations pendentes. Retorna quantas foram aplicadas.

    Recebe uma conexao ja aberta. Nao abre pool. Levanta MigrationError
    para qualquer inconsistencia.
    """
    pasta = (
        migrations_dir if migrations_dir is not None else _migrations_dir_padrao()
    )

    await conn.execute(CREATE_SCHEMA_MIGRATIONS)
    await conn.execute("SELECT pg_advisory_lock($1)", ADVISORY_LOCK_KEY)

    aplicadas = 0
    try:
        arquivos = sorted(pasta.glob("*.sql"))
        if not arquivos:
            raise MigrationError(f"nenhuma migration encontrada em {pasta}")

        for caminho in arquivos:
            nome = caminho.name
            sha = _sha256(caminho)

            row = await conn.fetchrow(
                "SELECT sha256 FROM schema_migrations WHERE filename = $1",
                nome,
            )

            if row is not None:
                if row["sha256"] == sha:
                    print(f"SKIP  {nome}")
                    continue
                raise MigrationError(
                    f"migration ja aplicada com SHA-256 diferente: {nome}\n"
                    f"  registrado: {row['sha256']}\n"
                    f"  atual:      {sha}"
                )

            sql = caminho.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename, sha256) "
                    "VALUES ($1, $2)",
                    nome,
                    sha,
                )
            print(f"APPLY {nome}")
            aplicadas += 1
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_KEY)

    return aplicadas


async def _main() -> int:
    conn = await asyncpg.connect(settings().database_url)
    try:
        n = await aplicar(conn)
        print(f"OK: {n} migration(s) aplicada(s)")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except MigrationError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
