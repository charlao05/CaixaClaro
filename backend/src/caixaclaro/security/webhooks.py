"""Autenticacao de webhooks por header secreto - M10a."""

import secrets

from fastapi import Request

from .erros import erro


def verificar_header_token(
    request: Request,
    header_name: str,
    esperado: str | None,
) -> None:
    """Compara header de webhook em tempo constante."""
    if not esperado:
        raise erro(401, "WEBHOOK_NAO_CONFIGURADO")

    recebido = request.headers.get(header_name)

    if not recebido or not secrets.compare_digest(recebido, esperado):
        raise erro(401, "WEBHOOK_NAO_AUTORIZADO")
