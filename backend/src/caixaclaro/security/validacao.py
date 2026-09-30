"""Validacoes de formato de dominio — sem criptografia."""


def validar_cpf(cpf: str) -> bool:
    """Valida CPF brasileiro (11 digitos) com digitos verificadores.

    Rejeita:
    - comprimento diferente de 11
    - todos os digitos iguais (000..., 111..., ..., 999...)
    - primeiro digito verificador incorreto
    - segundo digito verificador incorreto
    """
    digitos = "".join(c for c in cpf if c.isdigit())
    if len(digitos) != 11:
        return False
    if digitos == digitos[0] * 11:
        return False

    soma = sum(int(digitos[i]) * (10 - i) for i in range(9))
    resto = soma % 11
    dv1 = 0 if resto < 2 else 11 - resto
    if int(digitos[9]) != dv1:
        return False

    soma = sum(int(digitos[i]) * (11 - i) for i in range(10))
    resto = soma % 11
    dv2 = 0 if resto < 2 else 11 - resto
    return int(digitos[10]) == dv2