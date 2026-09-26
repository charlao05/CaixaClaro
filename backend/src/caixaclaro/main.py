from contextlib import asynccontextmanager
from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from .api import auth,perfil
from .config import settings
from .db import abrir_pool,fechar_pool
@asynccontextmanager
async def lifespan(app):
    await abrir_pool(); yield; await fechar_pool()
def criar_app():
    app=FastAPI(title="CaixaClaro",version="0.1.0",lifespan=lifespan)
    @app.exception_handler(StarletteHTTPException)
    async def handler_http(request:Request,exc):
        if isinstance(exc.detail,dict) and "erro" in exc.detail: return JSONResponse(status_code=exc.status_code,content=exc.detail)
        return JSONResponse(status_code=exc.status_code,content={"erro":str(exc.detail),"mensagem":str(exc.detail)})
    @app.exception_handler(RequestValidationError)
    async def handler_validacao(request:Request,exc):
        return JSONResponse(status_code=422,content={"erro":"VALIDATION_ERROR","mensagem":"Dados inválidos.","detalhes":exc.errors()})
    app.include_router(auth.router,prefix="/api/v1/auth",tags=["auth"])
    app.include_router(perfil.router,prefix="/api/v1/perfil",tags=["perfil"])
    @app.get("/health")
    async def health(): return {"ok":True,"ambiente":settings().ambiente}
    return app
app=criar_app()
