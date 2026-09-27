import json


async def test_eval_ultima_execucao_404_quando_snapshot_nao_existe(
    client, monkeypatch, tmp_path
):
    from caixaclaro.api import eval as eval_api

    caminho = tmp_path / "ultima_execucao.json"

    class Settings:
        eval_ultima_execucao_path = str(caminho)

    monkeypatch.setattr(eval_api, "settings", lambda: Settings())

    r = await client.get("/api/v1/eval/ultima-execucao")

    assert r.status_code == 404
    assert r.json()["erro"] == "EVAL_ULTIMA_EXECUCAO_NAO_DISPONIVEL"


async def test_eval_ultima_execucao_retorna_snapshot_existente(
    client, monkeypatch, tmp_path
):
    from caixaclaro.api import eval as eval_api

    caminho = tmp_path / "ultima_execucao.json"

    esperado = {
        "executado_em": "2026-09-27T20:44:48.391844+00:00",
        "commit": "dd339394d4e232b11b970b3b50bab3f583701d53",
        "taxonomia_version": "v1",
        "total": 34,
        "avaliaveis": 26,
        "abstratidos": 8,
        "metricas": {
            "A": 0,
            "B": 1.0,
            "C": 0.235,
            "D": 0,
        },
        "por_dificuldade": {
            "easy": {"total": 20, "abst": 0, "acertos": 20},
            "medium": {"total": 6, "abst": 0, "acertos": 6},
            "hard": {"total": 3, "abst": 3, "acertos": 0},
            "adversarial": {"total": 5, "abst": 5, "acertos": 0},
        },
        "resultado": "PASS",
    }

    caminho.write_text(
        json.dumps(esperado, ensure_ascii=False),
        encoding="utf-8",
    )

    class Settings:
        eval_ultima_execucao_path = str(caminho)

    monkeypatch.setattr(eval_api, "settings", lambda: Settings())

    r = await client.get("/api/v1/eval/ultima-execucao")

    assert r.status_code == 200
    assert r.json() == esperado


async def test_eval_ultima_execucao_500_quando_snapshot_e_invalido(
    client, monkeypatch, tmp_path
):
    from caixaclaro.api import eval as eval_api

    caminho = tmp_path / "ultima_execucao.json"
    caminho.write_text("{json invalido", encoding="utf-8")

    class Settings:
        eval_ultima_execucao_path = str(caminho)

    monkeypatch.setattr(eval_api, "settings", lambda: Settings())

    r = await client.get("/api/v1/eval/ultima-execucao")

    assert r.status_code == 500
    assert r.json()["erro"] == "EVAL_ULTIMA_EXECUCAO_INVALIDA"
