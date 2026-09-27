"""Entry point do worker persistente.

Uso:
  cd backend
  python -m caixaclaro.workers

Loop infinito; processa um sync por tick. Ctrl+C encerra limpo.
"""
import asyncio
import os
import signal
import sys
import uuid

from ..db import abrir_pool, conexao, fechar_pool
from ..services.workers import processar_um_sync

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"
TICK_INTERVALO = float(os.environ.get("WORKER_TICK_INTERVALO", "2.0"))


async def _loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            async with conexao() as conn:
                fez = await processar_um_sync(conn, WORKER_ID)
        except Exception as e:
            print(f"[{WORKER_ID}] erro no tick: {e}", file=sys.stderr)
            fez = False

        if not fez:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=TICK_INTERVALO)
            except asyncio.TimeoutError:
                pass


async def _main() -> None:
    await abrir_pool()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows
    print(f"[{WORKER_ID}] iniciado")
    try:
        await _loop(stop_event)
    finally:
        await fechar_pool()
        print(f"[{WORKER_ID}] encerrado")


if __name__ == "__main__":
    asyncio.run(_main())
