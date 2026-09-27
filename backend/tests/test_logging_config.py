"""Testes do logging estruturado - M10a."""
import json
import logging
import sys

from caixaclaro.logging_config import JsonFormatter, setup_logging


def _record(level=logging.INFO, msg="hello", exc_info=None):
    return logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )


def test_formatter_produz_json_valido():
    f = JsonFormatter()
    data = json.loads(f.format(_record()))
    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "hello"
    assert "timestamp" in data


def test_formatter_mescla_extras():
    f = JsonFormatter()
    r = _record()
    r.event = "custom"
    r.worker_id = "w-1"
    data = json.loads(f.format(r))
    assert data["event"] == "custom"
    assert data["worker_id"] == "w-1"


def test_formatter_serializa_excecao():
    f = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        data = json.loads(f.format(_record(exc_info=sys.exc_info())))
    assert "exception" in data
    assert "ValueError" in data["exception"]
    assert "boom" in data["exception"]


def test_formatter_valor_nao_serializavel_vira_string():
    f = JsonFormatter()
    r = _record()
    r.event = object()
    data = json.loads(f.format(r))
    assert isinstance(data["event"], str)


def test_setup_logging_idempotente():
    setup_logging()
    root = logging.getLogger()
    n1 = len(root.handlers)
    setup_logging()
    n2 = len(root.handlers)
    assert n1 == n2
    assert n1 >= 1


def test_setup_logging_usa_json_formatter():
    setup_logging()
    root = logging.getLogger()
    assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)
