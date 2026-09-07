"""Ejecución automática diaria (§29)."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None
JOB_ID = "daily_job_search"


def _run_daily() -> None:
    from app.pipeline.runner import run_pipeline

    logger.info("corrida diaria automática iniciada")
    try:
        result = asyncio.run(run_pipeline("scheduled"))
        logger.info("corrida diaria terminada: %s nuevos, %s recomendados",
                    result["new_jobs"], result["recommended"])
    except Exception:  # noqa: BLE001
        logger.exception("la corrida diaria falló")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone=settings.timezone)
    _scheduler.add_job(
        _run_daily,
        CronTrigger(hour=settings.daily_run_hour, minute=settings.daily_run_minute,
                    timezone=settings.timezone),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("scheduler activo: %02d:%02d %s", settings.daily_run_hour,
                settings.daily_run_minute, settings.timezone)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def next_run_time():
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    return job.next_run_time if job else None
