"""Health e readiness — M10a."""
from contextlib import asynccontextmanager

import pytest


async def test_healthz_responde_200(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_readyz_responde_200_com_db_ok(client):
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ---------------------------------------------------------------------------
# O monitor externo (M10.C) depende do que vem abaixo.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", ["/healthz", "/readyz"])
async def test_saude_responde_a_head(client, caminho):
    """Monitores de uptime e `curl -I` sondam com HEAD. Até 2026-10-10 a
    resposta era 405 (rota só-GET no FastAPI): o monitor acusaria queda com
    o site no ar."""
    r = await client.head(caminho)
    assert r.status_code == 200


@asynccontextmanager
async def _banco_fora_do_ar():
    raise ConnectionError("banco indisponível (simulado)")
    yield  # pragma: no cover


@pytest.mark.parametrize("metodo", ["GET", "HEAD"])
async def test_readyz_responde_503_quando_o_banco_nao_responde(
    client, monkeypatch, metodo
):
    """É este 503 que o monitor externo precisa enxergar. O HEAD devolve o
    mesmo código do GET — não pode dizer "tudo bem" com o banco fora."""
    from caixaclaro import db

    monkeypatch.setattr(db, "conexao", _banco_fora_do_ar)
    r = await client.request(metodo, "/readyz")
    assert r.status_code == 503
    if metodo == "GET":
        assert r.json() == {"ok": False}


@pytest.mark.parametrize("metodo", ["GET", "HEAD"])
async def test_healthz_nao_depende_do_banco(client, monkeypatch, metodo):
    """Liveness continua 200 com o banco fora: é o que separa "processo
    morto" de "dependência fora" na hora de ler o alerta."""
    from caixaclaro import db

    monkeypatch.setattr(db, "conexao", _banco_fora_do_ar)
    r = await client.request(metodo, "/healthz")
    assert r.status_code == 200


async def test_head_nao_aparece_no_esquema_da_api(client):
    """O HEAD é detalhe operacional; o esquema público continua só com GET."""
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    for caminho in ("/healthz", "/readyz"):
        assert set(r.json()["paths"][caminho]) == {"get"}
