import asyncio, sys
from caixaclaro.security.crypto import decifrar_cpf
from caixaclaro.db import abrir_pool, fechar_pool, conexao

async def go():
    await abrir_pool()
    try:
        async with conexao() as c:
            row = await c.fetchrow(
                "SELECT cpf_cifrado FROM users WHERE cpf_cifrado IS NOT NULL LIMIT 1"
            )
            if row is None:
                print("SKIP: sem cpf_cifrado no banco")
                return 0
            cpf = decifrar_cpf(row["cpf_cifrado"])
            if len(cpf) != 11:
                print(f"FAIL: cpf len={len(cpf)}")
                return 1
            print(f"OK: cpf decifrado len={len(cpf)}")
            return 0
    finally:
        await fechar_pool()

sys.exit(asyncio.run(go()))
