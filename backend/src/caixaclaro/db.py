from contextlib import asynccontextmanager
import asyncpg
from .config import settings
_pool=None
async def abrir_pool():
    global _pool
    if _pool is None:
        _pool=await asyncpg.create_pool(dsn=settings().database_url,min_size=2,max_size=10,command_timeout=30)
async def fechar_pool():
    global _pool
    if _pool is not None:
        await _pool.close(); _pool=None
@asynccontextmanager
async def conexao():
    if _pool is None: raise RuntimeError("Pool do banco não inicializado.")
    async with _pool.acquire() as conn: yield conn
