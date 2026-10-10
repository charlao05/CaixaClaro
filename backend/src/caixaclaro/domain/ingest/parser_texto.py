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
    r"\s([-+]?\s*(?:R\$\s*)?(?:[\d.]+,\d{2}|\d+\.\d{2})(?:\s*[DCdc])?)\s*$"
)
# Colagem "em colunas": data, descricao e valor em linhas separadas.
_RE_SO_DATA = re.compile(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$")
_RE_SO_VALOR = re.compile(
    r"^[-+]?\s*(?:R\$\s*)?[-+]?\s*(?:[\d.]+,\d{2}|\d+\.\d{2})(?:\s*[DCdc])?$"
)


def _ano(y: str | None, ref: int) -> int:
    if not y:
        return ref
    v = int(y)
    return v + 2000 if v < 100 else v


def _data(dia: str, mes: str, ano: str | None, ano_ref: int, hoje: date) -> date:
    """Monta a data. Sem ano na linha, assume o ano de referencia — mas um
    extrato nao traz lancamento do futuro: se a data cair depois de hoje,
    ela e do ano anterior (ex.: "28/12" colado em janeiro)."""
    dt = date(_ano(ano, ano_ref), int(mes), int(dia))
    if not ano and dt > hoje:
        dt = date(dt.year - 1, dt.month, dt.day)
    return dt


def _parse_em_colunas(linhas: list[str], ano_ref: int, hoje: date) -> list[LancamentoBruto]:
    """Aceita o formato copiado de tabelas e apps: uma linha so com a data,
    depois a descricao, depois uma linha so com o valor."""
    out: list[LancamentoBruto] = []
    data_atual: date | None = None
    descricao: list[str] = []
    for linha in linhas:
        m = _RE_SO_DATA.match(linha)
        if m:
            try:
                data_atual = _data(m.group(1), m.group(2), m.group(3), ano_ref, hoje)
            except ValueError:
                data_atual = None
            descricao = []
            continue
        if data_atual is None:
            continue
        if _RE_SO_VALOR.match(linha):
            negativo = linha.lstrip().startswith("-") or re.search(r"R\$\s*-", linha)
            v = parse_valor_bancario(re.sub(r"[-+]|R\$", "", linha))
            if v is not None and descricao:
                out.append(LancamentoBruto(
                    data_atual, " ".join(descricao), -abs(v) if negativo else v
                ))
                descricao = []
            continue
        descricao.append(linha)
    return out


def parse_texto(
    texto: str, *, ano_referencia: int | None = None, hoje: date | None = None
) -> list[LancamentoBruto]:
    hoje = hoje or date.today()
    ano_ref = ano_referencia if ano_referencia is not None else hoje.year
    if not texto or not texto.strip():
        raise ExtratoIlegivel("O texto está vazio.")

    out: list[LancamentoBruto] = []
    for linha in (l.strip() for l in texto.splitlines()):
        if not linha:
            continue
        md = _RE_DATA.match(linha)
        if not md:
            continue  # não começa com data → cabeçalho/rodapé/separador
        mv = _RE_VALOR_FIM.search(linha)
        if not mv:
            raise ExtratoIlegivel(
                f"Não encontrei o valor no fim desta linha: {linha}"
            )
        try:
            dt = _data(md.group(1), md.group(2), md.group(3), ano_ref, hoje)
        except ValueError as e:
            raise ExtratoIlegivel(f"A data desta linha não existe: {linha}") from e
        v = parse_valor_bancario(mv.group(1))
        if v is None:
            raise ExtratoIlegivel(f"Não consegui ler o valor desta linha: {linha}")
        desc = linha[md.end():mv.start()].strip()
        if not desc:
            raise ExtratoIlegivel(f"Esta linha está sem descrição: {linha}")
        out.append(LancamentoBruto(dt, desc, v))

    if not out:
        linhas = [l.strip() for l in texto.splitlines() if l.strip()]
        out = _parse_em_colunas(linhas, ano_ref, hoje)

    if not out:
        raise ExtratoIlegivel(
            "Não reconheci nenhum lançamento. Cada lançamento precisa ter "
            "data (dia/mês), descrição e valor."
        )
    return out
