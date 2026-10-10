"""Testes do logging estruturado - M10a."""
import io
import json
import logging
import sys

import httpx

from caixaclaro.logging_config import JsonFormatter, mascarar, setup_logging


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


# ---------------------------------------------------------------------------
# Revisão de 2026-10-09, achado R9: token do bot e CPF no log
# ---------------------------------------------------------------------------

TOKEN = "1234567890:TOKEN_FALSO_DE_TESTE_abc-XYZ"
CPF = "52998224725"


def test_mascarar_oculta_token_do_bot_e_cpf():
    assert TOKEN not in mascarar(f"POST https://api.telegram.org/bot{TOKEN}/sendMessage")
    assert mascarar(f"/bot{TOKEN}/sendMessage") == "/bot<token-ocultado>/sendMessage"
    assert mascarar(f"GET /customers?cpfCnpj={CPF}") == "GET /customers?cpfCnpj=<ocultado>"
    assert mascarar("titular 529.982.247-25") == "titular <cpf-ocultado>"
    assert mascarar(f'erro do provedor: "CPF {CPF} invalido"') == (
        'erro do provedor: "CPF <11-digitos-ocultados> invalido"'
    )
    # Não mexe no que não é segredo.
    for comum in ("R$ 1.234,56", "2026-10-09", "valor 1234567890", "bot do grupo"):
        assert mascarar(comum) == comum


def test_formatter_mascara_mensagem_extras_e_excecao():
    f = JsonFormatter()
    r = _record(msg=f"falhou /bot{TOKEN}/sendMessage")
    r.url = f"/customers?cpfCnpj={CPF}"
    try:
        raise RuntimeError(f"erro em /bot{TOKEN}/getMe")
    except RuntimeError:
        r.exc_info = sys.exc_info()
    linha = f.format(r)
    assert TOKEN not in linha
    assert CPF not in linha
    json.loads(linha)  # continua sendo JSON válido


def test_setup_logging_silencia_url_da_biblioteca_http():
    setup_logging()
    for nome in ("httpx", "httpcore"):
        assert not logging.getLogger(nome).isEnabledFor(logging.INFO), nome


def _cliente_falso(monkeypatch, resposta):
    original = httpx.AsyncClient

    class ClienteFalso(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(lambda req: resposta)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", ClienteFalso)


def _capturar_log():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logging.getLogger().addHandler(handler)
    return buf, handler


async def test_envio_real_pelo_telegram_nao_poe_o_token_no_log(monkeypatch):
    """Reprodução da auditoria com a função real de envio."""
    from caixaclaro.services import telegram_bot

    setup_logging()
    monkeypatch.setattr(telegram_bot, "_config", lambda: (TOKEN, "https://api.telegram.org"))
    _cliente_falso(monkeypatch, httpx.Response(200, json={"ok": True}))
    raiz = logging.getLogger()
    nivel = raiz.level
    raiz.setLevel(logging.INFO)
    buf, handler = _capturar_log()
    try:
        await telegram_bot.enviar_mensagem(123, "oi")
        # Mesmo que alguém volte a ligar o INFO do httpx, a linha sai mascarada.
        logging.getLogger("httpx").setLevel(logging.INFO)
        await telegram_bot.enviar_mensagem(123, "oi")
    finally:
        logging.getLogger().removeHandler(handler)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        raiz.setLevel(nivel)
    log = buf.getvalue()
    assert TOKEN not in log
    assert log.count("HTTP Request") == 1  # só a segunda chamada, já mascarada
    assert "bot<token-ocultado>" in log


async def test_busca_real_de_cliente_no_asaas_nao_poe_o_cpf_no_log(monkeypatch):
    from caixaclaro.services import asaas

    setup_logging()
    monkeypatch.setattr(asaas, "_config", lambda: ("chave", "https://asaas.invalido"))
    _cliente_falso(monkeypatch, httpx.Response(200, json={"data": []}))
    raiz = logging.getLogger()
    nivel = raiz.level
    raiz.setLevel(logging.INFO)
    buf, handler = _capturar_log()
    try:
        assert await asaas.buscar_customer_por_cpf(CPF) is None
        logging.getLogger("httpx").setLevel(logging.INFO)
        assert await asaas.buscar_customer_por_cpf(CPF) is None
    finally:
        logging.getLogger().removeHandler(handler)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        raiz.setLevel(nivel)
    log = buf.getvalue()
    assert CPF not in log
    assert "cpfCnpj=<ocultado>" in log
