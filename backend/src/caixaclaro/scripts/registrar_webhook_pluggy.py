"""Registra webhook de aplicacao na Pluggy com header customizado.

Uso:
    docker compose exec api python -m caixaclaro.scripts.registrar_webhook_pluggy <URL>

Requer PLUGGY_WEBHOOK_SECRET no .env. A URL e parametro operacional
(muda a cada restart do quick tunnel). Executar novamente atualiza
o webhook existente no lado Pluggy.
"""
import asyncio
import sys

from caixaclaro.config import settings
from caixaclaro.services.pluggy import registrar_webhook_pluggy


async def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("USO: python -m caixaclaro.scripts.registrar_webhook_pluggy <URL>")
        print("Ex.: ... https://tune-noted-donor-radar.trycloudflare.com")
        return 1

    base = argv[0].rstrip("/")
    url = f"{base}/api/v1/webhooks/pluggy"

    s = settings()
    if not s.pluggy_webhook_secret:
        print("ERRO: PLUGGY_WEBHOOK_SECRET ausente no .env")
        return 2

    print(f"URL        : {url}")
    print(f"secret len : {len(s.pluggy_webhook_secret)}")
    print("Registrando...")

    try:
        resultado = await registrar_webhook_pluggy(url, s.pluggy_webhook_secret)
    except Exception as e:
        print(f"ERRO: {e}")
        return 3

    print("OK. Resposta Pluggy:")
    print(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
