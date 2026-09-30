import asyncio

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..config import settings
from ..db import conexao
from ..security.audit import hash_email, registrar_auditoria
from ..security.auth import (
    hash_senha,
    verificar_senha,
    criar_sessao,
    gerar_token,
    revogar_sessao,
)
from ..security.crypto import hash_cpf, cifrar_cpf
from ..security.erros import erro
from ..security.rate_limit import limitador_login, limitador_register
from ..security.validacao import validar_cpf


router = APIRouter()
_bearer = HTTPBearer(auto_error=True)


class RegistroIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    senha: str = Field(min_length=8, max_length=72)
    cpf: str


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    senha: str = Field(min_length=1, max_length=72)


def _cpf_digitos(cpf: str) -> str:
    return "".join(c for c in cpf if c.isdigit())


async def _aplicar_atraso(segundos: float) -> None:
    if segundos > 0:
        await asyncio.sleep(segundos)


def _ip_do_request(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def _ua_do_request(request: Request) -> str:
    return request.headers.get("user-agent", "")


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(dados: RegistroIn, response: Response, request: Request):
    ip = _ip_do_request(request)
    chave = f"register:ip:{ip}"

    bloqueio = limitador_register.bloqueio(chave)
    if bloqueio > 0:
        raise erro(
            429,
            "RATE_LIMIT",
            f"Muitas tentativas. Tente novamente em {bloqueio} segundos.",
            headers={"Retry-After": str(bloqueio)},
        )

    if limitador_register.contar(chave) >= limitador_register.limite:
        raise erro(
            429,
            "RATE_LIMIT",
            "Muitas tentativas de cadastro. Tente novamente mais tarde.",
            headers={"Retry-After": str(limitador_register.janela_segundos)},
        )

    limitador_register.registrar(chave)

    cpf_digitos = _cpf_digitos(dados.cpf)

    if not validar_cpf(cpf_digitos):
        raise erro(400, "CPF_INVALIDO", "CPF inválido.")

    cpf_h = hash_cpf(cpf_digitos)

    async with conexao() as conn:
        if await conn.fetchval(
            "SELECT 1 FROM users WHERE email = $1",
            dados.email,
        ):
            raise erro(409, "EMAIL_EM_USO", "E-mail já cadastrado.")

        if await conn.fetchval(
            "SELECT 1 FROM users WHERE cpf_hash = $1",
            cpf_h,
        ):
            raise erro(409, "CPF_EM_USO", "CPF já cadastrado.")

        user_id = await conn.fetchval(
            "INSERT INTO users "
            "(email, senha_hash, cpf_hash, cpf_cifrado, regime) "
            "VALUES ($1,$2,$3,$4,'MEI') RETURNING id",
            dados.email,
            hash_senha(dados.senha),
            cpf_h,
            cifrar_cpf(cpf_digitos),
        )

    sid, expira_em = await criar_sessao(str(user_id))
    token = gerar_token(str(user_id), sid, expira_em)

    response.headers["Location"] = "/api/v1/perfil"

    return {
        "token": token,
        "expires_at": expira_em.isoformat(),
        "user": {
            "id": str(user_id),
            "email": dados.email,
            "nome": None,
            "regime": "MEI",
        },
    }


@router.post("/login")
async def login(dados: LoginIn, request: Request):
    ip = _ip_do_request(request)
    ua = _ua_do_request(request)
    email_hash = hash_email(str(dados.email))

    chave_ip = f"login:ip:{ip}"
    chave_email = f"login:email:{email_hash}"

    segundos_ip = limitador_login.bloqueio(chave_ip)
    segundos_email = limitador_login.bloqueio(chave_email)

    if segundos_ip > 0 or segundos_email > 0:
        segundos = max(segundos_ip, segundos_email)

        raise erro(
            429,
            "RATE_LIMIT",
            f"Muitas tentativas. Tente novamente em {segundos} segundos.",
            headers={"Retry-After": str(segundos)},
        )

    atraso = max(
        limitador_login.atraso(chave_ip),
        limitador_login.atraso(chave_email),
    )
    await _aplicar_atraso(atraso)

    async with conexao() as conn:
        u = await conn.fetchrow(
            "SELECT id, email, nome, regime, senha_hash "
            "FROM users WHERE email = $1",
            dados.email,
        )

    if u is None or not verificar_senha(dados.senha, u["senha_hash"]):
        limitador_login.registrar(chave_ip)
        limitador_login.registrar(chave_email)

        async with conexao() as conn:
            await registrar_auditoria(
                conn,
                ator="sistema",
                acao="login_falha",
                alvo=email_hash,
                meta={
                    "email_hash": email_hash,
                    "ip": ip,
                    "user_agent": ua,
                },
            )

        raise erro(
            401,
            "CREDENCIAIS_INVALIDAS",
            "Credenciais inválidas.",
        )

    limitador_login.limpar(chave_ip)
    limitador_login.limpar(chave_email)

    async with conexao() as conn:
        await registrar_auditoria(
            conn,
            ator="usuario",
            acao="login",
            user_id=str(u["id"]),
            alvo=str(u["id"]),
            meta={
                "ip": ip,
                "user_agent": ua,
            },
        )

    sid, expira_em = await criar_sessao(str(u["id"]))
    token = gerar_token(str(u["id"]), sid, expira_em)

    return {
        "token": token,
        "expires_at": expira_em.isoformat(),
        "user": {
            "id": str(u["id"]),
            "email": u["email"],
            "nome": u["nome"],
            "regime": u["regime"],
        },
    }


@router.post("/logout")
async def logout(
    cred: HTTPAuthorizationCredentials = Depends(_bearer),
):
    try:
        payload = jwt.decode(
            cred.credentials,
            settings().jwt_secret,
            algorithms=["HS256"],
        )
    except JWTError:
        raise erro(401, "UNAUTHORIZED")

    sid = payload.get("sid")

    if not sid:
        raise erro(401, "UNAUTHORIZED")

    await revogar_sessao(sid)

    return {"ok": True}
