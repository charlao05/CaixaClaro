from fastapi import APIRouter, Depends, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from pydantic import BaseModel, ConfigDict, EmailStr
from ..config import settings
from ..db import conexao
from ..security.auth import (
    hash_senha, verificar_senha, criar_sessao, gerar_token, revogar_sessao,
)
from ..security.crypto import hash_cpf, cifrar_cpf
from ..security.erros import erro

router = APIRouter()
_bearer = HTTPBearer(auto_error=True)


class RegistroIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    senha: str
    cpf: str


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    senha: str


def _cpf_digitos(cpf: str) -> str:
    return "".join(c for c in cpf if c.isdigit())


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(dados: RegistroIn, response: Response):
    cpf_digitos = _cpf_digitos(dados.cpf)
    if len(cpf_digitos) != 11:
        raise erro(400, "CPF_INVALIDO", "CPF inválido.")
    cpf_h = hash_cpf(cpf_digitos)

    async with conexao() as conn:
        if await conn.fetchval("SELECT 1 FROM users WHERE email = $1", dados.email):
            raise erro(409, "EMAIL_EM_USO", "E-mail já cadastrado.")
        if await conn.fetchval("SELECT 1 FROM users WHERE cpf_hash = $1", cpf_h):
            raise erro(409, "CPF_EM_USO", "CPF já cadastrado.")

        user_id = await conn.fetchval(
            "INSERT INTO users (email, senha_hash, cpf_hash, cpf_cifrado, regime) "
            "VALUES ($1,$2,$3,$4,'MEI') RETURNING id",
            dados.email, hash_senha(dados.senha), cpf_h, cifrar_cpf(cpf_digitos),
        )

    sid, expira_em = await criar_sessao(str(user_id))
    token = gerar_token(str(user_id), sid, expira_em)

    response.headers["Location"] = "/api/v1/perfil"

    return {
        "token": token,
        "expires_at": expira_em.isoformat(),
        "user": {"id": str(user_id), "email": dados.email, "nome": None, "regime": "MEI"},
    }


@router.post("/login")
async def login(dados: LoginIn):
    async with conexao() as conn:
        u = await conn.fetchrow(
            "SELECT id, email, nome, regime, senha_hash FROM users WHERE email = $1",
            dados.email,
        )
    if u is None or not verificar_senha(dados.senha, u["senha_hash"]):
        raise erro(401, "CREDENCIAIS_INVALIDAS", "Credenciais inválidas.")

    sid, expira_em = await criar_sessao(str(u["id"]))
    token = gerar_token(str(u["id"]), sid, expira_em)
    return {
        "token": token,
        "expires_at": expira_em.isoformat(),
        "user": {"id": str(u["id"]), "email": u["email"], "nome": u["nome"], "regime": u["regime"]},
    }


@router.post("/logout")
async def logout(cred: HTTPAuthorizationCredentials = Depends(_bearer)):
    try:
        payload = jwt.decode(cred.credentials, settings().jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise erro(401, "UNAUTHORIZED")
    sid = payload.get("sid")
    if not sid:
        raise erro(401, "UNAUTHORIZED")
    await revogar_sessao(sid)
    return {"ok": True}
