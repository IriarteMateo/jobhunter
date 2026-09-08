"""Aplicación FastAPI."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import jobs, misc
from app.config import settings
from app.db import init_db, session_scope
from app.scheduler import start_scheduler, stop_scheduler
from app.seed import seed_companies, seed_profile
from app.services.profile import get_user
from app.sources.registry import sync_source_catalog

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with session_scope() as db:
        get_user(db)
        seed_profile(db)
        seed_companies(db)
        sync_source_catalog(db)
    if settings.scheduler_enabled:
        start_scheduler()
    logger.info("%s listo · IA=%s · DB=%s", settings.app_name, settings.ai_provider,
                settings.database_url.split("://")[0])
    yield
    stop_scheduler()


app = FastAPI(
    title="AI Job Hunter",
    description="Buscador y ranking inteligente de empleos para perfiles junior en Buenos Aires.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(misc.router)


@app.get("/api/health")
def health():
    """Incluye la base y la carpeta en uso.

    Sin esto, un servidor levantado por error desde otra copia del proyecto se
    ve exactamente igual que el correcto, sólo que con la app vacía.
    """
    from app.config import BASE_DIR

    return {
        "status": "ok",
        "app": settings.app_name,
        "ai_provider": settings.ai_provider,
        "database": settings.database_url,
        "project_dir": str(BASE_DIR.parent),
    }


@app.get("/api/version")
def version():
    """Commit que está corriendo ahora mismo.

    La app se actualiza sola en segundo plano (`auto-update.sh` hace `git pull`
    cada tanto). La pantalla consulta esto cada minuto y, cuando el commit
    cambia, se recarga: así las mejoras aparecen sin que nadie toque nada.
    """
    import subprocess

    from app.config import BASE_DIR

    proyecto = BASE_DIR.parent
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=proyecto, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - sin git la app funciona igual
        commit = ""
    return {"commit": commit or "sin-git"}
