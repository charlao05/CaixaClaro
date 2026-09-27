from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import abrir_pool, fechar_pool
from .api import auth, billing, contas, perfil, sync, transacoes, webhooks


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
                "detalhes": exc.errors(),
            },
        )

    app.include_router(auth.router,   prefix="/api/v1/auth",   tags=["auth"])
    app.include_router(perfil.router, prefix="/api/v1/perfil", tags=["perfil"])
    app.include_router(transacoes.router, prefix="/api/v1/transacoes", tags=["transacoes"])
    app.include_router(contas.router,    prefix="/api/v1/contas",    tags=["contas"])
    app.include_router(webhooks.router,  prefix="/api/v1/webhooks",  tags=["webhooks"])
    app.include_router(sync.router,      prefix="/api/v1/sync",      tags=["sync"])
    app.include_router(billing.router,   prefix="/api/v1/billing",   tags=["billing"])
    app.include_router(billing.payments_router, prefix="/api/v1/payments", tags=["payments"])

    @app.get("/health")
    async def health():
        return {"ok": True, "ambiente": settings().ambiente}

    return app


app = criar_app()
