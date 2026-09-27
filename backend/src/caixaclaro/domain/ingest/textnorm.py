"""Normalização para identidade do paste — CONTRATOS_INTERNOS §16."""
import hashlib
import unicodedata


def normalizar(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = " ".join(s.split())
    return s.strip()


def calcular_paste_id(texto: str) -> str:
    normalizado = normalizar(texto)
    digest = hashlib.sha256(normalizado.encode("utf-8")).hexdigest()
    return digest[:16]
