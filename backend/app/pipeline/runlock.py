"""Lock compartido entre TODAS las formas de disparar el pipeline.

Hay tres entradas posibles —el botón de la app, el agente diario de launchd y
un cron externo— y las tres escriben la misma base. Dos corridas simultáneas
sobre SQLite terminan en "database is locked" y un 500 en la cara del usuario.

El lock es un archivo, no una variable: tiene que funcionar entre procesos
distintos, no sólo dentro del servidor web.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

LOCK_FILE = BASE_DIR / ".pipeline.lock"
# Una corrida completa tarda ~2 minutos. Pasado este margen, el lock quedó
# huérfano por un proceso que murió y se puede reclamar.
STALE_MINUTES = 45


class RunInProgress(RuntimeError):
    """Ya hay una corrida en curso."""

    def __init__(self, desde: datetime | None = None):
        self.desde = desde
        minutos = ""
        if desde:
            minutos = f" (empezó hace {int((datetime.now() - desde).total_seconds() // 60)} min)"
        super().__init__(f"Ya hay una búsqueda en curso{minutos}.")


def _iniciada_hace() -> datetime | None:
    try:
        return datetime.fromtimestamp(LOCK_FILE.stat().st_mtime)
    except OSError:
        return None


def esta_corriendo() -> bool:
    inicio = _iniciada_hace()
    if inicio is None:
        return False
    return (datetime.now() - inicio).total_seconds() / 60 < STALE_MINUTES


def acquire() -> None:
    """Toma el lock. Lanza RunInProgress si ya está tomado."""
    if esta_corriendo():
        raise RunInProgress(_iniciada_hace())
    if LOCK_FILE.exists():
        logger.warning("lock huérfano de una corrida anterior: se reclama")
        LOCK_FILE.unlink(missing_ok=True)
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")


def release() -> None:
    LOCK_FILE.unlink(missing_ok=True)
