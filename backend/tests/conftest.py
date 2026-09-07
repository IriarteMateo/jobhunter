"""Fixtures compartidas: base en memoria y avisos reales anonimizados.

La base de test se fija ANTES de importar cualquier módulo de la app. Antes se
recargaban los módulos con importlib para cambiarla, y eso re-registraba las
tablas sobre el mismo metadata de SQLAlchemy: funcionaba o no según el orden en
que pytest importaba los archivos de test.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile

_TEST_DB = pathlib.Path(tempfile.gettempdir()) / "jobhunter_pytest.db"
_TEST_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ENABLE_HTML_SCRAPING"] = "false"
os.environ["ENABLE_BROWSER_RENDERING"] = "false"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def sample_jobs() -> list[dict]:
    return json.loads((FIXTURES / "jobs.json").read_text(encoding="utf-8"))


@pytest.fixture
def db():
    """Sesión SQLite en memoria con el schema completo."""
    from app.db import Base
    from app import models  # noqa: F401

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def candidate():
    from app.pipeline.scoring import CandidateContext

    return CandidateContext(
        years_experience=0.0,
        degree_field="Negocios Digitales",
        university="Universidad de San Andrés",
        language_codes={"es": "Nativo", "en": "C1", "de": "C1"},
        skills=["excel", "sql", "power bi", "google analytics"],
        role_families=["business", "product", "data", "operations"],
        preferred_locations=["San Isidro", "Vicente López", "Martínez"],
        is_graduated=True,
    )


@pytest.fixture(autouse=True, scope="session")
def _lock_aislado(tmp_path_factory):
    """El lock del pipeline vive en el directorio del proyecto y lo comparte la
    app en marcha. Sin aislarlo, correr los tests con la app abierta daba 409."""
    from app.pipeline import runlock

    runlock.LOCK_FILE = tmp_path_factory.mktemp("lock") / ".pipeline.lock"
    yield
