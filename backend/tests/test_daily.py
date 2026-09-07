"""Tests de la corrida diaria disparada por el sistema operativo."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from app import daily
from app.pipeline import runlock


@pytest.fixture(autouse=True)
def clean_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(runlock, "LOCK_FILE", tmp_path / ".pipeline.lock")
    monkeypatch.setattr(daily, "LOG_FILE", tmp_path / "logs" / "daily.log")
    yield
    runlock.LOCK_FILE.unlink(missing_ok=True)


def test_lock_is_acquired_once():
    assert daily._acquire_lock() is True
    assert daily._acquire_lock() is False, "dos corridas simultáneas se pisarían"
    daily._release_lock()
    assert daily._acquire_lock() is True


def test_lock_is_released():
    daily._acquire_lock()
    daily._release_lock()
    assert not runlock.LOCK_FILE.exists()


def test_lock_stores_the_pid():
    daily._acquire_lock()
    assert runlock.LOCK_FILE.read_text(encoding="utf-8") == str(os.getpid())


def test_stale_lock_from_a_crashed_run_is_reclaimed():
    """Si una corrida murió a mitad de camino, el lock no puede bloquear para siempre."""
    runlock.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    runlock.LOCK_FILE.write_text("99999", encoding="utf-8")
    old = (datetime.now() - timedelta(minutes=runlock.STALE_MINUTES + 5)).timestamp()
    os.utime(runlock.LOCK_FILE, (old, old))
    assert daily._acquire_lock() is True


def test_a_recent_lock_is_respected():
    runlock.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    runlock.LOCK_FILE.write_text("99999", encoding="utf-8")
    assert daily._acquire_lock() is False


def test_daily_module_is_runnable_as_a_script():
    """launchd invoca `python -m app.daily`: tiene que existir ese entrypoint."""
    import importlib.util

    assert importlib.util.find_spec("app.daily") is not None
    assert callable(daily.main)


def test_desktop_notification_escapes_quotes():
    """El título de un aviso puede traer comillas: AppleScript no tiene escapes."""
    from app.services.notifications import _applescript_quote

    assert '"' not in _applescript_quote('Analyst "Senior"').replace('\\"', "")
    assert "\n" not in _applescript_quote("linea1\nlinea2")


# ------------------- el lock lo comparten TODAS las entradas ---------------- #
def test_the_lock_is_shared_by_every_entry_point():
    """El botón de la app, launchd y un cron externo escriben la misma base.

    Dos corridas simultáneas sobre SQLite terminan en "database is locked" y un
    500 en la cara del usuario: pasó de verdad con dos corridas solapadas.
    """
    runlock.acquire()
    with pytest.raises(runlock.RunInProgress):
        runlock.acquire()
    runlock.release()
    runlock.acquire()          # liberado, se puede volver a tomar
    runlock.release()


def test_a_crashed_run_does_not_block_forever():
    import os
    from datetime import datetime, timedelta

    runlock.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    runlock.LOCK_FILE.write_text("99999", encoding="utf-8")
    viejo = (datetime.now() - timedelta(minutes=runlock.STALE_MINUTES + 5)).timestamp()
    os.utime(runlock.LOCK_FILE, (viejo, viejo))
    runlock.acquire()          # no debe lanzar
    runlock.release()


def test_run_in_progress_says_when_it_started():
    runlock.acquire()
    try:
        runlock.acquire()
    except runlock.RunInProgress as exc:
        assert "búsqueda en curso" in str(exc)
    finally:
        runlock.release()
