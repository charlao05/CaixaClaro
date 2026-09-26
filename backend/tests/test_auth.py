import uuid
from jose import jwt as jose_jwt
async def test_health(client):
    assert (await client.get("/health")).status_code==200
async def test_register_retorna_201_com_jwt(client):
    r=await client.post("/api/v1/auth/register",json={"email":"maria@example.com","senha":"senha_segura_123","cpf":"123.456.789-00"})
    assert r.status_code==201 and "token" in r.json() and "expires_at" in r.json()
    assert r.json()["user"]["email"]=="maria@example.com" and r.headers["Location"]=="/api/v1/perfil"
async def test_email_duplicado_retorna_409(client):
    d={"email":"x@x.com","senha":"senha123","cpf":"111.111.111-11"}
    assert (await client.post("/api/v1/auth/register",json=d)).status_code==201
    r=await client.post("/api/v1/auth/register",json=d); assert r.status_code==409 and r.json()["erro"]=="EMAIL_EM_USO"
async def test_cpf_duplicado_retorna_409(client):
    await client.post("/api/v1/auth/register",json={"email":"a@a.com","senha":"senha123","cpf":"111.111.111-11"})
    r=await client.post("/api/v1/auth/register",json={"email":"b@b.com","senha":"senha123","cpf":"111.111.111-11"})
    assert r.status_code==409 and r.json()["erro"]=="CPF_EM_USO"
async def test_cpf_invalido_retorna_400(client):
    r=await client.post("/api/v1/auth/register",json={"email":"a@a.com","senha":"senha123","cpf":"123"})
    assert r.status_code==400 and r.json()["erro"]=="CPF_INVALIDO"
async def test_register_rejeita_campos_extras(client):
    r=await client.post("/api/v1/auth/register",json={"email":"c@c.com","senha":"senha123","cpf":"222.222.222-22","nome":"X"})
    assert r.status_code==422 and r.json()["erro"]=="VALIDATION_ERROR"
async def test_login_retorna_jwt(client):
    await client.post("/api/v1/auth/register",json={"email":"b@b.com","senha":"senha123","cpf":"222.222.222-22"})
    r=await client.post("/api/v1/auth/login",json={"email":"b@b.com","senha":"senha123"})
    assert r.status_code==200 and "token" in r.json()
async def test_login_senha_errada_retorna_401(client):
    await client.post("/api/v1/auth/register",json={"email":"c@c.com","senha":"senha123","cpf":"333.333.333-33"})
    r=await client.post("/api/v1/auth/login",json={"email":"c@c.com","senha":"errada"})
    assert r.status_code==401 and r.json()["erro"]=="CREDENCIAIS_INVALIDAS"
async def test_logout_revoga_sessao(client):
    r=await client.post("/api/v1/auth/register",json={"email":"d@d.com","senha":"senha123","cpf":"444.444.444-44"})
    h={"Authorization":"Bearer "+r.json()["token"]}
    assert (await client.get("/api/v1/perfil",headers=h)).status_code==200
    assert (await client.post("/api/v1/auth/logout",headers=h)).status_code==200
    assert (await client.get("/api/v1/perfil",headers=h)).status_code==401
async def test_perfil_sem_token_retorna_401(client):
    r=await client.get("/api/v1/perfil"); assert r.status_code==401 and r.json()["erro"]=="UNAUTHORIZED"
async def test_jwt_exp_igual_sessions_expira_em(client):
    from caixaclaro.db import conexao
    r=await client.post("/api/v1/auth/register",json={"email":"exp@example.com","senha":"senha123","cpf":"888.888.888-88"})
    p=jose_jwt.get_unverified_claims(r.json()["token"])
    async with conexao() as conn: row=await conn.fetchrow("SELECT expira_em FROM sessions WHERE id=$1",uuid.UUID(p["sid"]))
    assert row is not None and int(p["exp"])==int(row["expira_em"].timestamp())
