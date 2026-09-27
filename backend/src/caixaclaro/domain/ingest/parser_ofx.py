"""Parser de OFX."""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .parser_texto import ExtratoIlegivel, LancamentoBruto


_RE_BLOCO = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.DOTALL | re.IGNORECASE)
_RE_DTPOSTED = re.compile(r"<DTPOSTED>(\d{8})", re.IGNORECASE)
_RE_TRNAMT = re.compile(r"<TRNAMT>([-+]?[\d.]+)", re.IGNORECASE)
_RE_MEMO = re.compile(r"<MEMO>([^<\r\n]+)", re.IGNORECASE)
_RE_NAME = re.compile(r"<NAME>([^<\r\n]+)", re.IGNORECASE)
_RE_OFX_TAG = re.compile(r"<OFX\s*>", re.IGNORECASE)


def _decodificar(bruto: bytes) -> str:
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("latin-1")


def parse_ofx(bruto: bytes) -> list[LancamentoBruto]:
    texto = _decodificar(bruto)

    # Checagem estrutural: exige a tag <OFX> como marcador do formato.
    # Não basta procurar a substring "OFX" — qualquer texto pode contê-la.
    if not _RE_OFX_TAG.search(texto):
        raise ExtratoIlegivel("Arquivo não é OFX (tag <OFX> ausente).")

    blocos = _RE_BLOCO.findall(texto)
    if not blocos:
        return []  # OFX válido sem lançamentos

    out: list[LancamentoBruto] = []
    for bloco in blocos:
        m_dt = _RE_DTPOSTED.search(bloco)
        m_am = _RE_TRNAMT.search(bloco)
        if not m_dt or not m_am:
            raise ExtratoIlegivel("Bloco STMTTRN sem DTPOSTED ou TRNAMT.")
        try:
            dt = datetime.strptime(m_dt.group(1), "%Y%m%d").date()
        except ValueError as e:
            raise ExtratoIlegivel(f"DTPOSTED inválido: {m_dt.group(1)}") from e
        try:
            v = Decimal(m_am.group(1))
        except InvalidOperation as e:
            raise ExtratoIlegivel(f"TRNAMT inválido: {m_am.group(1)}") from e
        m_desc = _RE_MEMO.search(bloco) or _RE_NAME.search(bloco)
        desc = (m_desc.group(1).strip() if m_desc else "") or "(sem descrição)"
        out.append(LancamentoBruto(dt, desc, v))

    return out
