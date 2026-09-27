"""Configuracao de logging em JSON para producao - M10a.

Escopo:
- Runtime (API, worker)
- Falhas de integracao (Telegram)

Fora de escopo:
- CLIs (eval/runner, migration_runner) mantem print() como saida de terminal.
"""
import json
import logging
import sys
from datetime import datetime, timezone


_RESERVED = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


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
        return json.dumps(base, ensure_ascii=False, default=str)


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

    _configured = True
