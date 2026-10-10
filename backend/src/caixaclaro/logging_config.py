"""Configuracao de logging em JSON para producao - M10a.

Escopo:
- Runtime (API, worker)
- Falhas de integracao (Telegram)

Fora de escopo:
- CLIs (eval/runner, migration_runner) mantem print() como saida de terminal.

Segredos (revisao de 2026-10-09, achado R9): a biblioteca HTTP (httpx)
registra cada requisicao em INFO com a URL completa. A URL do Telegram leva
o token do bot (/bot<TOKEN>/sendMessage) e a busca de cliente no Asaas leva
o CPF (?cpfCnpj=...). Com a raiz em INFO, as duas coisas iam para o log de
producao. CONTRATOS_INTERNOS §2: "CPF claro nunca em log de aplicacao".
Duas barreiras:
  1. httpx/httpcore so registram de WARNING para cima;
  2. toda linha formatada passa por `mascarar` (token de bot e CPF), o que
     cobre tambem mensagens de excecao e campos extras.
"""
import json
import logging
import re
import sys
from datetime import datetime, timezone


_RESERVED = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


# Bibliotecas que registram a URL inteira de cada requisicao em INFO.
_REGISTRAM_URL = ("httpx", "httpcore")

_MASCARAS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Token do bot do Telegram: /bot<id numerico>:<segredo>/...
    (re.compile(r"bot\d{5,}:[A-Za-z0-9_-]{10,}"), "bot<token-ocultado>"),
    # CPF/CNPJ em query string (busca de cliente no Asaas).
    (re.compile(r"(cpfCnpj=)[0-9.\-/]+"), r"\1<ocultado>"),
    # CPF formatado em qualquer texto.
    (re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "<cpf-ocultado>"),
    # CPF sem pontuação (11 dígitos soltos) — por exemplo, numa mensagem de
    # erro devolvida por um provedor. Pode ocultar outro número de 11
    # dígitos (um celular com DDD); no log, isso é aceitável.
    (re.compile(r"\b\d{11}\b"), "<11-digitos-ocultados>"),
)


def mascarar(texto: str) -> str:
    """Oculta token de bot do Telegram e CPF num texto de log."""
    for padrao, troca in _MASCARAS:
        texto = padrao.sub(troca, texto)
    return texto


class JsonFormatter(logging.Formatter):
    """Formata LogRecord como uma linha JSON.

    Campos sempre presentes: timestamp, level, logger, message.
    Campos extras passados via extra passam a integrar o objeto.
    Excecoes sao serializadas em `exception`.
    """

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k in _RESERVED or k.startswith("_"):
                continue
            base[k] = v
        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)
        return mascarar(json.dumps(base, ensure_ascii=False, default=str))


_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configura o root logger com saida JSON em stdout.

    Idempotente: chamadas subsequentes sao no-op.
    """
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    for nome in _REGISTRAM_URL:
        logging.getLogger(nome).setLevel(max(level, logging.WARNING))

    _configured = True
