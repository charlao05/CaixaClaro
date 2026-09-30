"""Gerador de CPF valido para fixtures de teste.

Espelha o algoritmo de security/validacao.py por conveniencia de teste.
NAO deve ser usado em testes que verificam o algoritmo em si — esses
usam CPFs hardcoded conhecidos.
"""


def cpf_valido(base9: str) -> str:
    """Gera CPF (11 digitos, sem mascara) a partir de 9 digitos-base."""
    d = base9[:9]
    if len(d) != 9 or not d.isdigit():
        raise ValueError("base9 precisa ter 9 digitos")

    soma = sum(int(d[i]) * (10 - i) for i in range(9))
    r = soma % 11
    d += str(0 if r < 2 else 11 - r)

    soma = sum(int(d[i]) * (11 - i) for i in range(10))
    r = soma % 11
    d += str(0 if r < 2 else 11 - r)

    return d