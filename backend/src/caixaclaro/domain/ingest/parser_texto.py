"""Parser de extrato colado."""
import re
from datetime import date
from decimal import Decimal

from .valor import parse_valor_bancario


class ExtratoIlegivel(Exception):
    pass


class LancamentoBruto:
    __slots__ = ("data", "descricao", "valor")

    def __init__(self, data: date, descricao: str, valor: Decimal):
        self.data = data
        self.descricao = descricao
        self.valor = valor


_RE_DATA = re.compile(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\s+")
_RE_VALOR_FIM = re.compile(
    r"\s([-+]?\s*(?:R\$\s*)?[\d.]+,\d{2}(?:\s*[DCdc])?)\s*$"
)


def _ano(y: str | None, ref: int) -> int:
    if not y:
        return ref
    v = int(y)
    return v + 2000 if v < 100 else v


def parse_texto(
    texto: str, *, ano_referencia: int | None = None
) -> list[LancamentoBruto]:
    ano_ref = ano_referencia if ano_referencia is not None else date.today().year
    if not texto or not texto.strip():
        raise ExtratoIlegivel("Texto vazio.")

    out: list[LancamentoBruto] = []
    for linha in (l.strip() for l in texto.splitlines()):
        if not linha:
            continue
        md = _RE_DATA.match(linha)
        if not md:
            continue  # não começa com data → cabeçalho/rodapé/separador
        mv = _RE_VALOR_FIM.search(linha)
        if not mv:
            raise ExtratoIlegivel(f"Linha sem valor: {linha!r}")
        try:
            dt = date(_ano(md.group(3), ano_ref), int(md.group(2)), int(md.group(1)))
        except ValueError as e:
            raise ExtratoIlegivel(f"Data inválida: {linha!r}") from e
        v = parse_valor_bancario(mv.group(1))
        if v is None:
            raise ExtratoIlegivel(f"Valor inválido: {linha!r}")
        desc = linha[md.end():mv.start()].strip()
        if not desc:
            raise ExtratoIlegivel(f"Descrição vazia: {linha!r}")
        out.append(LancamentoBruto(dt, desc, v))

    if not out:
        raise ExtratoIlegivel("Nenhum lançamento reconhecido.")
    return out
