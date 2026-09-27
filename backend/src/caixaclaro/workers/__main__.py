"""Entry point do worker persistente.

Uso:
  cd backend
  python -m caixaclaro.workers

Duas tasks concorrentes:
  - sync: processa sync_requests pendentes (intervalo curto)
  - renewal: varre subscriptions vencidas (intervalo 6h)

Ctrl+C encerra limpo.
"""
import asyncio
import os
import signal
import sys
import uuid

from ..db import abrir_pool, conexao, fechar_pool
from ..services.renewal import renovar_assinaturas
from ..services.workers import processar_um_sync

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"
TICK_INTERVALO = float(os.environ.get("WORKER_TICK_INTERVALO", "2.0"))
RENEWAL_INTERVALO = float(os.environ.get("WORKER_RENEWAL_INTERVALO", "21600"))


async def _loop_sync(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            async with conexao() as conn:
                fez = await processar_um_sync(conn, WORKER_ID)
        except Exception as e:
            print(f"[{WORKER_ID}] erro no sync tick: {e}", file=sys.stderr)
            fez = False

        if not fez:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=TICK_INTERVALO)
            except asyncio.TimeoutError:
                pass


async def _loop_renewal(stop_event: asyncio.Event) -> None:
    from ..config import settings
    if not settings().asaas_api_key:
        print(
            f"[{WORKER_ID}] renewal: ASAAS_API_KEY ausente — task nao iniciada",
            file=sys.stderr,
        )
        return

    # Roda uma vez ao iniciar, depois a cada RENEWAL_INTERVALO.
    while not stop_event.is_set():
        try:
            async with conexao() as conn:
                stats = await renovar_assinaturas(conn, WORKER_ID)
            if stats["total"] > 0:
                print(f"[{WORKER_ID}] renewal: {stats}", file=sys.stderr)
        except Exception as e:
            print(f"[{WORKER_ID}] erro no renewal: {e}", file=sys.stderr)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RENEWAL_INTERVALO)
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
        await asyncio.gather(
            _loop_sync(stop_event),
            _loop_renewal(stop_event),
        )
    finally:
        await fechar_pool()
        print(f"[{WORKER_ID}] encerrado")


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass

