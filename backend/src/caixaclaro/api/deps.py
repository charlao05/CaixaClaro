from fastapi import Depends
from ..security.auth import usuario_atual


async def usuario(u: dict = Depends(usuario_atual)) -> dict:
    return u
