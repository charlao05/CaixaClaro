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
import logging
import os
import signal
import uuid

from ..db import abrir_pool, conexao, fechar_pool
from ..logging_config import setup_logging
from ..services.renewal import renovar_assinaturas
from ..services.workers import processar_um_sync

setup_logging()
logger = logging.getLogger(__name__)

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"
TICK_INTERVALO = float(os.environ.get("WORKER_TICK_INTERVALO", "2.0"))
RENEWAL_INTERVALO = float(os.environ.get("WORKER_RENEWAL_INTERVALO", "21600"))


async def _loop_sync(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            async with conexao() as conn:
                fez = await processar_um_sync(conn, WORKER_ID)
        except Exception as e:
            logger.error("sync_tick_failed", extra={"worker_id": WORKER_ID, "error": str(e)})
            fez = False

        if not fez:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=TICK_INTERVALO)
            except asyncio.TimeoutError:
                pass


async def _loop_renewal(stop_event: asyncio.Event) -> None:
    from ..config import settings
    if not settings().asaas_api_key:
        logger.warning(
            "renewal_disabled",
            extra={"worker_id": WORKER_ID, "reason": "asaas_api_key_missing"},
        )
        return

    # Roda uma vez ao iniciar, depois a cada RENEWAL_INTERVALO.
    while not stop_event.is_set():
        try:
            async with conexao() as conn:
                stats = await renovar_assinaturas(conn, WORKER_ID)
            if stats["total"] > 0:
                logger.info("renewal_run", extra={"worker_id": WORKER_ID, "stats": stats})
        except Exception as e:
            logger.error("renewal_failed", extra={"worker_id": WORKER_ID, "error": str(e)})

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
    logger.info("worker_started", extra={"worker_id": WORKER_ID})
    try:
        await asyncio.gather(
            _loop_sync(stop_event),
            _loop_renewal(stop_event),
        )
    finally:
        await fechar_pool()
        logger.info("worker_stopped", extra={"worker_id": WORKER_ID})


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass

