"""Auth conforme docs/CONTRATOS_INTERNOS.md §1."""
from datetime import datetime, timedelta, timezone
import uuid
import bcrypt as _bcrypt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from ..config import settings
from ..db import conexao
from .erros import erro

_bearer = HTTPBearer(auto_error=False)


def hash_senha(senha: str) -> str:
    return _bcrypt.hashpw(
        senha.encode("utf-8"),
        _bcrypt.gensalt(),
    ).decode("utf-8")


def verificar_senha(senha: str, h: str) -> bool:
    try:
        return _bcrypt.checkpw(
            senha.encode("utf-8"),
            h.encode("utf-8"),
        )
    except Exception:
        return False


async def criar_sessao(user_id: str) -> tuple[str, datetime]:
    sid = uuid.uuid4()
    expira_em = (
        datetime.now(timezone.utc).replace(microsecond=0)
        + timedelta(minutes=settings().jwt_expira_minutos)
    )
    async with conexao() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, user_id, expira_em) VALUES ($1,$2,$3)",
            sid,
            uuid.UUID(user_id),
            expira_em,
        )
    return str(sid), expira_em


def gerar_token(user_id: str, session_id: str, expira_em: datetime) -> str:
    payload = {
        "sub": user_id,
        "sid": session_id,
        "iat": datetime.now(timezone.utc),
        "exp": int(expira_em.timestamp()),
    }
    return jwt.encode(
        payload,
        settings().jwt_secret,
        algorithm="HS256",
    )


async def revogar_sessao(session_id: str) -> None:
    async with conexao() as conn:
        await conn.execute(
            "UPDATE sessions SET revogada_em = now() "
            "WHERE id = $1 AND revogada_em IS NULL",
            uuid.UUID(session_id),
        )


async def usuario_atual(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if cred is None:
        raise erro(401, "UNAUTHORIZED")

    try:
        payload = jwt.decode(
            cred.credentials,
            settings().jwt_secret,
            algorithms=["HS256"],
        )
    except JWTError:
        raise erro(401, "UNAUTHORIZED")

    sid, sub = payload.get("sid"), payload.get("sub")
    if not sid or not sub:
        raise erro(401, "UNAUTHORIZED")

    async with conexao() as conn:
        sessao = await conn.fetchrow(
            "SELECT id, user_id FROM sessions "
            "WHERE id = $1 AND revogada_em IS NULL AND expira_em > now()",
            uuid.UUID(sid),
        )
        if sessao is None or str(sessao["user_id"]) != sub:
            raise erro(401, "UNAUTHORIZED")

        user = await conn.fetchrow(
            "SELECT id, email, nome, regime, mes_abertura_mei, ano_abertura_mei, "
            "telegram_chat_id, criado_em, atualizado_em FROM users WHERE id = $1",
            uuid.UUID(sub),
        )
        if user is None:
            raise erro(401, "UNAUTHORIZED")

        return dict(user)
