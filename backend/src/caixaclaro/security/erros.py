from fastapi import HTTPException


def erro(
    status_code: int,
    codigo: str,
    mensagem: str | None = None,
    headers: dict[str, str] | None = None,
    extra: dict | None = None,
) -> HTTPException:
    """Resposta de erro padrao do projeto.

    'extra' permite acrescentar chaves ao 'detail' sem quebrar o contrato
    existente. Quando None ou {}, o payload e' exatamente o de antes:

        {"detail": {"erro": <codigo>, "mensagem": <mensagem>}}

    Quando presente, as chaves sao mescladas APOS 'erro' e 'mensagem'.
    Chaves reservadas ('erro', 'mensagem') em 'extra' nao sobrescrevem
    as originais.
    """
    detail: dict = {"erro": codigo, "mensagem": mensagem or codigo}
    if extra:
        for k, v in extra.items():
            if k in ("erro", "mensagem"):
                continue
            detail[k] = v
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers=headers,
    )