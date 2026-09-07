"""Entrada para la corrida diaria desde el sistema operativo.

El scheduler interno (APScheduler) sólo existe mientras la app web está
levantada. Este módulo permite que macOS (launchd) o cualquier cron dispare la
búsqueda aunque la app esté cerrada:

    backend/.venv/bin/python -m app.daily

Usa un lock para que dos corridas nunca se pisen (por ejemplo si la app está
abierta y launchd dispara al mismo tiempo).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from app.config import BASE_DIR, settings
from app.pipeline import runlock

LOG_FILE = BASE_DIR / "logs" / "daily.log"


def _setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)],
    )


# El lock vive en app/pipeline/runlock.py: lo comparten el agente diario, el
# botón de la app y cualquier cron externo.
def _acquire_lock() -> bool:
    """True si se pudo tomar el lock."""
    try:
        runlock.acquire()
        return True
    except runlock.RunInProgress:
        return False


def _release_lock() -> None:
    runlock.release()


def main() -> int:
    _setup_logging()
    logger = logging.getLogger("jobhunter.daily")

    if not _acquire_lock():
        logger.warning("ya hay una corrida en curso: se omite esta ejecución")
        return 0

    try:
        from app.db import init_db, session_scope
        from app.pipeline.runner import run_pipeline
        from app.seed import seed_companies, seed_profile
        from app.services.profile import get_user
        from app.sources.registry import sync_source_catalog

        init_db()
        with session_scope() as db:
            get_user(db)
            seed_profile(db)
            seed_companies(db)
            sync_source_catalog(db)

        logger.info("corrida diaria iniciada (disparada por el sistema)")
        _release_lock()   # run_pipeline toma el mismo lock
        result = asyncio.run(run_pipeline("scheduled"))
        logger.info(
            "corrida terminada: %s avisos revisados, %s nuevos, %s recomendados, %.1fs",
            result["raw_jobs"], result["new_jobs"], result["recommended"],
            result["duration_ms"] / 1000,
        )
        summary = {k: v for k, v in result.items() if k not in ("sources", "errors")}
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except Exception:  # noqa: BLE001 - se registra y se sale con código de error
        logger.exception("la corrida diaria falló")
        return 1
    finally:
        _release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
