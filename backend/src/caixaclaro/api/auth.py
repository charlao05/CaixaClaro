from typing import Literal
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..config import settings
from ..db import conexao
from ..security.audit import hash_email, registrar_auditoria
from ..security.auth import (
    criar_sessao,
    gerar_token,
    hash_senha,
    revogar_sessao,
    verificar_senha,
)
from ..security.crypto import cifrar_cpf, hash_cpf
from ..security.erros import erro
from ..security.rate_limit import limitador_login, limitador_register
from ..security.validacao import validar_cpf
import logging
import time
from collections import defaultdict, deque
from ..services import senha, telegram_bot

router = APIRouter()

logger = logging.getLogger(__name__)

# Rate limit especifico de reset de senha (IP-based, in-memory).
# Separado de limitador_login/register para nao misturar semantica.
_RESET_JANELA_S = 900.0
_RESET_LIMITE = 5
_reset_ts: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit_reset(chave: str) -> None:
    agora = time.monotonic()
    dq = _reset_ts[chave]
    while dq and agora - dq[0] > _RESET_JANELA_S:
        dq.popleft()
    if len(dq) >= _RESET_LIMITE:
        raise erro(
            429,
            "RATE_LIMIT",
            "Muitas tentativas. Tente novamente em 15 minutos.",
        )
    dq.append(agora)


def resetar_rate_limit() -> None:
    """Para testes: limpa o estado do limiter de reset."""
    _reset_ts.clear()
_bearer = HTTPBearer(auto_error=True)


class RegistroIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    senha: str = Field(min_length=8, max_length=72)
    cpf: str
    # Perfil informado pela pessoa no cadastro. Omitido => "MEI", que e o
    # comportamento historico da API (ver DECISOES 2026-10-09).
    regime: Literal["MEI", "SIMPLES", "PF"] | None = None


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
    regime = dados.regime or "MEI"

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
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            dados.email,
            hash_senha(dados.senha),
            cpf_h,
            cifrar_cpf(cpf_digitos),
            regime,
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
            "regime": regime,
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
    cred: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
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


class EsqueciSenhaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class RedefinirSenhaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    codigo: str = Field(min_length=6, max_length=6)
    nova_senha: str = Field(min_length=8, max_length=72)


@router.post("/esqueci-senha", status_code=202)
async def esqueci_senha(dados: EsqueciSenhaIn, request: Request):
    """Solicita recuperacao de senha. Resposta sempre 202.

    Se o email existe e tem telegram_chat_id, gera codigo de 6 digitos,
    salva hash em password_reset_tokens e envia via Telegram (best-effort).
    Caso contrario, nao faz nada. A resposta e indistinguivel de proposito.
    """
    ip = _ip_do_request(request)
    _rate_limit_reset(f"esqueci:ip:{ip}")
    email_hash = hash_email(str(dados.email))

    async with conexao() as conn:
        u = await conn.fetchrow(
            "SELECT id, telegram_chat_id FROM users WHERE email = $1",
            dados.email,
        )

        if u is not None and u["telegram_chat_id"] is not None:
            codigo = await senha.criar_solicitacao(conn, str(u["id"]))
            texto = (
                "CaixaClaro\n"
                f"Seu codigo de recuperacao: {codigo}\n"
                "Valido por 15 minutos.\n"
                "Se voce nao pediu, ignore esta mensagem."
            )
            try:
                await telegram_bot.enviar_mensagem(
                    int(u["telegram_chat_id"]), texto
                )
            except Exception as e:
                logger.warning(
                    "reset_telegram_send_failed",
                    extra={"error_type": type(e).__name__},
                )

        await registrar_auditoria(
            conn,
            ator="sistema",
            acao="esqueci_senha_solicitado",
            user_id=str(u["id"]) if u else None,
            alvo=email_hash,
            meta={
                "ip": ip,
                "tem_telegram": bool(u and u["telegram_chat_id"]),
            },
        )

    return {"ok": True}


@router.post("/redefinir-senha")
async def redefinir_senha(dados: RedefinirSenhaIn, request: Request):
    """Redefine a senha usando codigo de reset.

    Sucesso: troca o hash e revoga todas as sessoes do usuario.
    Erro: sempre 400 CODIGO_INVALIDO (email inexistente, codigo errado,
    expirado ou ja usado dao a mesma resposta).
    """
    ip = _ip_do_request(request)
    _rate_limit_reset(f"redefinir:ip:{ip}")

    async with conexao() as conn:
        u = await conn.fetchrow(
            "SELECT id FROM users WHERE email = $1",
            dados.email,
        )
        if u is None:
            raise erro(400, "CODIGO_INVALIDO", "Código inválido ou expirado.")

        uid = u["id"]
        async with conn.transaction():
            ok = await senha.consumir_codigo(conn, str(uid), dados.codigo)
            if not ok:
                raise erro(
                    400, "CODIGO_INVALIDO", "Código inválido ou expirado."
                )
            await conn.execute(
                "UPDATE users SET senha_hash = $1, atualizado_em = now() "
                "WHERE id = $2",
                hash_senha(dados.nova_senha),
                uid,
            )
            await conn.execute(
                "UPDATE sessions SET revogada_em = now() "
                "WHERE user_id = $1 AND revogada_em IS NULL",
                uid,
            )

        await registrar_auditoria(
            conn,
            ator="usuario",
            acao="senha_redefinida",
            user_id=str(uid),
            alvo=str(uid),
            meta={"ip": ip},
        )

    return {"ok": True}