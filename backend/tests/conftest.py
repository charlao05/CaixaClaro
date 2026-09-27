import os

import httpx
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


@pytest.fixture
async def client():
    from caixaclaro.main import criar_app

    app = criar_app()

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c


@pytest.fixture(autouse=True)
async def limpar_estado(client):
    from caixaclaro.db import conexao
    from caixaclaro.security import rate_limit

    rate_limit.resetar_tudo()

    async with conexao() as conn:
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
