"""Rate limiting in-memory por processo.

Válido para uma única instância. Não é proteção distribuída.
Migrar para Redis quando houver mais de uma instância rodando.
"""
import math
import time


class Limitador:
    def __init__(
        self,
        janela_segundos: int,
        limite: int,
        bloqueio_segundos: int = 0,
        atraso_progressivo: list[float] | None = None,
    ) -> None:
        self.janela_segundos = janela_segundos
        self.limite = limite
        self.bloqueio_segundos = bloqueio_segundos
        self.atraso_progressivo = list(atraso_progressivo or [])
        self._eventos: dict[str, list[float]] = {}
        self._bloqueios: dict[str, float] = {}

    def _limpar_antigos(self, chave: str, agora: float) -> None:
        if chave not in self._eventos:
            return

        limite_tempo = agora - self.janela_segundos
        self._eventos[chave] = [
            t for t in self._eventos[chave]
            if t > limite_tempo
        ]

        if not self._eventos[chave]:
            del self._eventos[chave]

    def registrar(self, chave: str) -> None:
        agora = time.monotonic()
        self._limpar_antigos(chave, agora)
        self._eventos.setdefault(chave, []).append(agora)

        if (
            self.bloqueio_segundos > 0
            and len(self._eventos[chave]) >= self.limite
        ):
            self._bloqueios[chave] = agora + self.bloqueio_segundos

    def contar(self, chave: str) -> int:
        agora = time.monotonic()
        self._limpar_antigos(chave, agora)
        return len(self._eventos.get(chave, []))

    def bloqueio(self, chave: str) -> int:
        agora = time.monotonic()
        desbloqueio = self._bloqueios.get(chave)

        if desbloqueio is None:
            return 0

        restante = desbloqueio - agora

        if restante <= 0:
            del self._bloqueios[chave]
            self._eventos.pop(chave, None)
            return 0

        return math.ceil(restante)

    def atraso(self, chave: str) -> float:
        if not self.atraso_progressivo:
            return 0.0

        n = self.contar(chave)

        if n < 5:
            return 0.0

        index = min(
            n - 5,
            len(self.atraso_progressivo) - 1,
        )

        return self.atraso_progressivo[index]

    def limpar(self, chave: str) -> None:
        self._eventos.pop(chave, None)
        self._bloqueios.pop(chave, None)

    def reset(self) -> None:
        self._eventos.clear()
        self._bloqueios.clear()


limitador_login = Limitador(
    janela_segundos=15 * 60,
    limite=10,
    bloqueio_segundos=15 * 60,
    atraso_progressivo=[0.5, 1.0, 2.0, 4.0],
)

limitador_register = Limitador(
    janela_segundos=60 * 60,
    limite=5,
)


def resetar_tudo() -> None:
    limitador_login.reset()
    limitador_register.reset()
