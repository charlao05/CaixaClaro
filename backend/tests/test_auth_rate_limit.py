from caixaclaro.security.rate_limit import limitador_login


async def _registrar_usuario(client, email="m2-rate@example.com"):
    resposta = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "senha": "senha-segura-123",
            "cpf": "12345678901",
        },
    )
    assert resposta.status_code == 201
    return resposta.json()


async def _falhar_login(client, email="m2-rate@example.com"):
    return await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "senha": "senha-errada",
        },
    )


async def test_login_bloqueia_apos_10_falhas(client):
    await _registrar_usuario(client)

    for _ in range(10):
        resposta = await _falhar_login(client)
        assert resposta.status_code == 401

    resposta = await _falhar_login(client)

    assert resposta.status_code == 429
    assert resposta.json()["erro"] == "RATE_LIMIT"
    assert "retry-after" in resposta.headers


async def test_login_sucesso_antes_do_bloqueio_limpa_contador(client):
    await _registrar_usuario(client)

    for _ in range(3):
        resposta = await _falhar_login(client)
        assert resposta.status_code == 401

    resposta = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "m2-rate@example.com",
            "senha": "senha-segura-123",
        },
    )
    assert resposta.status_code == 200

    for _ in range(3):
        resposta = await _falhar_login(client)
        assert resposta.status_code == 401

    assert limitador_login.contar("login:ip:127.0.0.1") == 3


async def test_register_bloqueia_apos_5_no_mesmo_ip(client):
    for i in range(5):
        resposta = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"m2-register-{i}@example.com",
                "senha": "senha-segura-123",
                "cpf": f"1234567890{i}",
            },
        )
        assert resposta.status_code == 201

    resposta = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "m2-register-6@example.com",
            "senha": "senha-segura-123",
            "cpf": "12345678901",
        },
    )

    assert resposta.status_code == 429
    assert resposta.json()["erro"] == "RATE_LIMIT"
    assert "retry-after" in resposta.headers


async def test_atraso_progressivo_e_aplicado(client):
    await _registrar_usuario(client, "m2-delay@example.com")

    for tentativa in range(1, 6):
        resposta = await _falhar_login(client, "m2-delay@example.com")
        assert resposta.status_code == 401
        assert limitador_login.atraso(
            "login:ip:127.0.0.1"
        ) == [0.0, 0.0, 0.0, 0.0, 0.5][tentativa - 1]

    resposta = await _falhar_login(client, "m2-delay@example.com")
    assert resposta.status_code == 401
    assert limitador_login.atraso("login:ip:127.0.0.1") == 1.0

    resposta = await _falhar_login(client, "m2-delay@example.com")
    assert resposta.status_code == 401
    assert limitador_login.atraso("login:ip:127.0.0.1") == 2.0

    resposta = await _falhar_login(client, "m2-delay@example.com")
    assert resposta.status_code == 401
    assert limitador_login.atraso("login:ip:127.0.0.1") == 4.0
