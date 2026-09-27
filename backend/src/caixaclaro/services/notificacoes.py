"""Notificacoes externas de alertas — M7.

Escopo: enviar alertas fiscais ja criados ao Telegram do usuario,
quando houver telegram_chat_id.

Best-effort: falhas sao logadas e nao propagam. Deve ser chamado
SEMPRE apos o COMMIT do alerta, nunca dentro da transacao — se o
Telegram estiver indisponivel, a transacao de banco ja fechou.
"""
from ..db import conexao
from . import telegram_bot


async def enviar_alertas_telegram(user_id, alertas) -> int:
    """Envia uma mensagem por alerta. Retorna quantas foram entregues.

    alertas: sequencia de (slug, severidade, mensagem).
    """
    if not alertas:
        return 0

    async with conexao() as conn:
        chat_id = await conn.fetchval(
            "SELECT telegram_chat_id FROM users WHERE id = $1",
            user_id,
        )
    if not chat_id:
        return 0

    enviados = 0
    for _slug, _sev, msg in alertas:
        try:
            await telegram_bot.enviar_mensagem(int(chat_id), msg)
            enviados += 1
        except Exception as e:
            print(f"[notificacoes] falha ao enviar alerta Telegram: {e}")
    return enviados
