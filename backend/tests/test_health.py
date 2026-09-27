"""Health e readiness — M10a."""


async def test_healthz_responde_200(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_readyz_responde_200_com_db_ok(client):
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
