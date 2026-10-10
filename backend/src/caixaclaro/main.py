from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import abrir_pool, fechar_pool
from .api import auth, billing, contas, perfil, sync, transacoes, webhooks, telegram
from .api import eval as eval_api
from .api import estoque, precificacao, produtos
from .logging_config import setup_logging


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await abrir_pool()
    yield
    await fechar_pool()


def criar_app() -> FastAPI:
    app = FastAPI(title="CaixaClaro", version="0.2.0", lifespan=lifespan)

    @app.exception_handler(StarletteHTTPException)
    async def handler_http(request: Request, exc: StarletteHTTPException):
        headers = exc.headers or {}
        detail = exc.detail
        if isinstance(detail, dict) and "erro" in detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=detail,
                headers=headers,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"erro": str(detail), "mensagem": str(detail)},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handler_validacao(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "erro": "VALIDATION_ERROR",
                "mensagem": "Dados inválidos.",
                "detalhes": jsonable_encoder(exc.errors()),
            },
        )

    app.include_router(auth.router,   prefix="/api/v1/auth",   tags=["auth"])
    app.include_router(eval_api.router, prefix="/api/v1/eval", tags=["eval"])
    app.include_router(perfil.router, prefix="/api/v1/perfil", tags=["perfil"])
    app.include_router(transacoes.router, prefix="/api/v1/transacoes", tags=["transacoes"])
    app.include_router(contas.router,    prefix="/api/v1/contas",    tags=["contas"])
    app.include_router(webhooks.router,  prefix="/api/v1/webhooks",  tags=["webhooks"])
    app.include_router(sync.router,      prefix="/api/v1/sync",      tags=["sync"])
    app.include_router(billing.router,   prefix="/api/v1/billing",   tags=["billing"])
    app.include_router(telegram.router, prefix="/api/v1/telegram", tags=["telegram"])
    app.include_router(billing.payments_router, prefix="/api/v1/payments", tags=["payments"])
    app.include_router(produtos.router,     prefix="/api/v1/produtos",     tags=["produtos"])
    app.include_router(estoque.router,      prefix="/api/v1/produtos",     tags=["estoque"])
    app.include_router(precificacao.router, prefix="/api/v1/precificacao", tags=["precificacao"])

    @app.get("/health")
    async def health():
        return {"ok": True, "ambiente": settings().ambiente}

    # /healthz e /readyz respondem tambem a HEAD. O FastAPI devolve 405 a
    # HEAD numa rota que so declara GET, e varios monitores de uptime (e o
    # `curl -I`) sondam com HEAD: sem isto, o monitor externo de /readyz
    # marcaria o site como fora do ar com tudo funcionando. O servidor nao
    # envia corpo em resposta a HEAD; o codigo de status e o mesmo do GET.
    @app.head("/healthz", include_in_schema=False)
    @app.get("/healthz")
    async def healthz():
        """Liveness: processo vivo, sem checar dependencias."""
        return {"ok": True}

    @app.head("/readyz", include_in_schema=False)
    @app.get("/readyz")
    async def readyz():
        """Readiness: pool do PostgreSQL utilizavel."""
        from .db import conexao
        try:
            async with conexao() as conn:
                await conn.fetchval("SELECT 1")
        except Exception:
            return JSONResponse(status_code=503, content={"ok": False})
        return {"ok": True}

    return app


app = criar_app()


