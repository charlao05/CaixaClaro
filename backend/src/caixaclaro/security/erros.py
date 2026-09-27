from fastapi import HTTPException


def erro(
    status_code: int,
    codigo: str,
    mensagem: str | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "erro": codigo,
            "mensagem": mensagem or codigo,
        },
        headers=headers,
    )
