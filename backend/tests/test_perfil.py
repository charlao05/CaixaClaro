async def _registrar(client,email,cpf):
    r=await client.post("/api/v1/auth/register",json={"email":email,"senha":"senha123","cpf":cpf})
    assert r.status_code==201
    return r.json()["token"]
async def test_get_perfil_retorna_dados_do_titular(client):
    r=await client.get("/api/v1/perfil",headers={"Authorization":"Bearer "+await _registrar(client,"p1@example.com","555.555.550-40")})
    assert r.status_code==200
    b=r.json(); assert b["email"]=="p1@example.com" and b["regime"]=="MEI"
    assert "cpf" not in b and "cpf_cifrado" not in b and "cpf_hash" not in b
async def test_patch_perfil_atualiza_nome(client):
    t=await _registrar(client,"p2@example.com","666.666.660-70"); h={"Authorization":"Bearer "+t}
    assert (await client.patch("/api/v1/perfil",json={"nome":"Maria Silva"},headers=h)).status_code==200
    assert (await client.get("/api/v1/perfil",headers=h)).json()["nome"]=="Maria Silva"
async def test_patch_perfil_rejeita_telegram_chat_id(client):
    t=await _registrar(client,"p3@example.com","777.777.770-09"); h={"Authorization":"Bearer "+t}
    r=await client.patch("/api/v1/perfil",json={"telegram_chat_id":99999},headers=h)
    assert r.status_code==422 and r.json()["erro"]=="VALIDATION_ERROR"
    assert (await client.get("/api/v1/perfil",headers=h)).json()["telegram_chat_id"] is None
