from fastapi import Depends

from ..db import conexao
from ..security.auth import usuario_atual
from ..security.erros import erro
from ..services.autorizacao import ContextoAutorizacao, decidir


async def usuario(u: dict = Depends(usuario_atual)) -> dict:
    """Autentica. Nao verifica direito de uso.

    Rotas que precisam continuar acessiveis apos o trial (billing,
    perfil, logout) dependem desta funcao, nao de 'usuario_ativo'.
    """
    return u


async def usuario_ativo(u: dict = Depends(usuario)) -> dict:
    """Autentica e verifica direito de uso.

    Rotas de produto dependem desta funcao. Em caso de bloqueio,
    levanta HTTP 402 ACESSO_BLOQUEADO.
    """
    async with conexao() as conn:
        row = await conn.fetchrow(
            "SELECT periodo_fim "
            "  FROM subscriptions "
            " WHERE user_id = $1 "
            " ORDER BY criado_em DESC, id DESC "
            " LIMIT 1",
            u["id"],
        )

    ctx = ContextoAutorizacao(
        trial_exempt=bool(u["trial_exempt"]),
        criado_em=u["criado_em"],
        periodo_fim=row["periodo_fim"] if row is not None else None,
        agora=None,
    )

    if not decidir(ctx):
        raise erro(
            402,
            "ACESSO_BLOQUEADO",
            "Assinatura ou periodo de teste expirado.",
        )

    return u