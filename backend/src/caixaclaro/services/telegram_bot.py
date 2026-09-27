"""Cliente Telegram Bot API — M7.

Escopo: envio de mensagens pelo bot usando a credencial configurada
em TELEGRAM_BOT_TOKEN.
"""
import httpx

from ..config import settings
from ..security.erros import erro


def _config() -> tuple[str, str]:
    s = settings()
    if not s.telegram_bot_token:
        raise erro(
            503,
            "TELEGRAM_NAO_CONFIGURADO",
            "Credencial Telegram ausente no ambiente.",
        )
    return s.telegram_bot_token, "https://api.telegram.org"


async def enviar_mensagem(chat_id: int, texto: str) -> dict:
    """Envia uma mensagem pelo Bot API do Telegram."""
    token, base = _config()

    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        r = await client.post(
            f"/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": texto,
            },
        )

    if r.status_code != 200:
        raise erro(
            502,
            "TELEGRAM_ENVIO_FALHOU",
            "Falha ao enviar mensagem pelo Telegram.",
        )

    return r.json()
