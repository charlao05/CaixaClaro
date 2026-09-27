import os
from pathlib import Path

import asyncpg
import httpx
import pytest_asyncio
import pytest
from httpx import ASGITransport

os.environ.setdefault("AMBIENTE", "dev")
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault(
    "CPF_HMAC_KEY",
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
)
os.environ.setdefault(
    "CPF_AES_KEY",
    "ZmVkY2JhOTg3NjU0MzIxMGZlZGNiYTk4NzY1NDMyMTA=",
)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://caixaclaro:dev_only_change_me@localhost:5432/caixaclaro",
)

os.environ.setdefault("PLUGGY_WEBHOOK_SECRET", "test-pluggy-secret")
os.environ.setdefault("ASAAS_WEBHOOK_TOKEN", "test-asaas-token")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-telegram-secret")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _aplicar_migracoes():
    """Aplica migrations/*.sql em ordem alfabetica, uma vez por sessao.

    Tolerante a reexecucao: se uma tabela/coluna/indice ja existe
    (porque o banco foi migrado manualmente), segue em frente.
    Nao usa tabela de controle — o estado do banco e a fonte de verdade.
    """
    from caixaclaro.config import settings

    raiz = Path(__file__).parent.parent
    migrations = sorted((raiz / "migrations").glob("*.sql"))
    if not migrations:
        return

    conn = await asyncpg.connect(settings().database_url)
    try:
        for sql_path in migrations:
            sql = sql_path.read_text(encoding="utf-8")
            # Cada statement em sua propria chamada: multi-statement aborta
            # tudo numa transacao implicita se um falhar. Split simples e
            # suficiente: as migrations nao tem funcoes nem dollar-quoting.
            for stmt in (s.strip() for s in sql.split(";") if s.strip()):
                try:
                    await conn.execute(stmt)
                except (
                    asyncpg.exceptions.DuplicateTableError,
                    asyncpg.exceptions.DuplicateObjectError,
                    asyncpg.exceptions.DuplicateColumnError,
                    asyncpg.exceptions.DuplicateSchemaError,
                ):
                    pass
    finally:
        await conn.close()


class _ClientComAuthWebhook:
    _AUTH = {
        "/webhooks/pluggy":   ("X-CaixaClaro-Webhook-Secret",     "test-pluggy-secret"),
        "/webhooks/asaas":    ("asaas-access-token",              "test-asaas-token"),
        "/webhooks/telegram": ("X-Telegram-Bot-Api-Secret-Token", "test-telegram-secret"),
    }

    def __init__(self, inner):
        self._inner = inner

    async def post(self, url, *args, headers=None, **kwargs):
        headers = dict(headers or {})
        for path, (nome, valor) in self._AUTH.items():
            if path in url:
                headers.setdefault(nome, valor)
                break
        return await self._inner.post(url, *args, headers=headers, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture
async def client():
    from caixaclaro.main import criar_app

    app = criar_app()

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield _ClientComAuthWebhook(c)


@pytest.fixture
async def client_sem_auth(client):
    return client._inner


@pytest.fixture(autouse=True)
async def limpar_estado(client):
    from caixaclaro.db import conexao
    from caixaclaro.security import rate_limit

    rate_limit.resetar_tudo()

    async with conexao() as conn:
        await conn.execute("DELETE FROM webhook_events")
        await conn.execute("DELETE FROM idempotency_keys")
        await conn.execute("DELETE FROM alerts")
        await conn.execute("DELETE FROM fiscal_state")
        await conn.execute("DELETE FROM transactions")
        await conn.execute("DELETE FROM audit_log")
        await conn.execute("DELETE FROM sessions")
        await conn.execute("DELETE FROM users")

    yield

    rate_limit.resetar_tudo()


@pytest.fixture(autouse=True)
def sem_atraso_real(monkeypatch):
    async def noop(_segundos: float) -> None:
        return None

    monkeypatch.setattr(
        "caixaclaro.api.auth._aplicar_atraso",
        noop,
    )
