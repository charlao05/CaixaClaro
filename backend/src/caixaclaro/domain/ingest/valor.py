"""Conversão de representações monetárias em Decimal."""
import re
from decimal import Decimal, InvalidOperation


_RE_MOEDA_INICIO = re.compile(r"^R\$\s*", re.IGNORECASE)
_RE_ESPACOS = re.compile(r"\s+")
_RE_EXP = re.compile(r"[0-9][eE][-+]?[0-9]")


def parse_valor_bancario(texto: str | None) -> Decimal | None:
    """
    Aceita:  "R$ 1.234,56", "-50,00", "1234.56", "1.234,56 D", "1.234,56 C".
    Rejeita: notação científica, vazio, formatos ambíguos.
    """
    if texto is None:
        return None
    s = texto.strip()
    if not s:
        return None

    s = _RE_MOEDA_INICIO.sub("", s)
    s = _RE_ESPACOS.sub("", s)
    if not s:
        return None

    sinal = None
    if s and s[-1] in "Dd":
        sinal = -1
        s = s[:-1]
    elif s and s[-1] in "Cc":
        sinal = 1
        s = s[:-1]
    if not s:
        return None

    if _RE_EXP.search(s):
        return None

    if "," in s:
        if s.count(",") > 1:
            return None
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")

    try:
        d = Decimal(s)
    except InvalidOperation:
        return None

    if sinal == -1:
        d = -abs(d)
    elif sinal == 1:
        d = abs(d)
    return d
