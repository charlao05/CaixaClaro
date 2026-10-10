"""Parser de CSV bancário."""
import csv
import io
import re
from datetime import date
from decimal import Decimal

from .valor import parse_valor_bancario
from .parser_texto import ExtratoIlegivel, LancamentoBruto


_RE_DATA = re.compile(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$")
_RE_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
# Bancos costumam por linhas de titulo antes do cabecalho de verdade.
MAX_LINHAS_PREAMBULO = 15


def _decodificar(bruto: bytes) -> str:
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("latin-1")


def _normalizar_nome(s: str) -> str:
    return s.strip().lower().replace("ç", "c").replace("ã", "a")


def _parse_data(s: str, ano_ref: int) -> date | None:
    iso = _RE_DATA_ISO.match(s.strip())
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    m = _RE_DATA.match(s.strip())
    if not m:
        return None
    y = int(m.group(3)) if m.group(3) else ano_ref
    if y < 100:
        y += 2000
    try:
        return date(y, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _detectar_delimitador(texto: str) -> str:
    """
    Detecção provisória. G5 (spec definitiva) segue pendente.

    Parseia a primeira linha com cada candidato e escolhe o que produz
    MAIS campos. Melhor que contagem bruta: vírgulas decimais dentro de
    um campo em CSV delimitado por ';' não confundem o parse.

    Fallback em empate: ';' (mais comum em extratos bancários brasileiros).
    """
    primeira = texto.split("\n", 1)[0]
    campos_pv = len(next(csv.reader([primeira], delimiter=";")))
    campos_virg = len(next(csv.reader([primeira], delimiter=",")))
    if campos_pv > campos_virg:
        return ";"
    if campos_virg > campos_pv:
        return ","
    return ";" if ";" in primeira else ","


def parse_csv(bruto: bytes) -> list[LancamentoBruto]:
    texto = _decodificar(bruto)
    if not texto.strip():
        raise ExtratoIlegivel("CSV vazio.")

    delimitador = _detectar_delimitador(texto)

    linhas = list(csv.reader(io.StringIO(texto), delimiter=delimitador))
    if not linhas:
        raise ExtratoIlegivel("CSV sem linhas.")

    def _e_cabecalho(celulas: list[str]) -> bool:
        return any("data" in c for c in celulas) and any(
            "valor" in c for c in celulas
        )

    # Pula linhas de titulo ("Extrato Conta Corrente", periodo, linha em
    # branco) ate achar o cabecalho real, se houver um logo no inicio.
    for i, linha in enumerate(linhas[:MAX_LINHAS_PREAMBULO]):
        if _e_cabecalho([_normalizar_nome(c) for c in linha]):
            linhas = linhas[i:]
            break

    primeira = [_normalizar_nome(c) for c in linhas[0]]
    tem_cabecalho = _e_cabecalho(primeira)

    idx_data = idx_desc = idx_valor = None
    if tem_cabecalho:
        for i, c in enumerate(primeira):
            if idx_data is None and "data" in c:
                idx_data = i
            elif idx_desc is None and ("descri" in c or "memo" in c or "hist" in c):
                idx_desc = i
            elif idx_valor is None and "valor" in c:
                idx_valor = i
        corpo = linhas[1:]
    else:
        idx_data, idx_desc, idx_valor = 0, 1, 2
        corpo = linhas

    if idx_data is None or idx_valor is None:
        raise ExtratoIlegivel(
            "Não encontrei as colunas de data e valor neste arquivo."
        )

    ano_ref = date.today().year
    out: list[LancamentoBruto] = []
    for n, linha in enumerate(corpo):
        if not linha or all(not c.strip() for c in linha):
            continue
        if len(linha) <= max(idx_data, idx_desc or 0, idx_valor):
            raise ExtratoIlegivel(
                f"A linha {n + 1} do arquivo está incompleta. "
                "Confira se é um extrato em CSV com data, descrição e valor."
            )
        dt = _parse_data(linha[idx_data], ano_ref)
        v = parse_valor_bancario(linha[idx_valor])
        if dt is None or v is None:
            raise ExtratoIlegivel(
                f"Não consegui ler a data ou o valor da linha {n + 1} do arquivo."
            )
        desc = linha[idx_desc].strip() if idx_desc is not None else ""
        out.append(LancamentoBruto(dt, desc, v))

    return out
