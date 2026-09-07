"""Arquitectura de adaptadores de fuentes (§35).

Cada fuente implementa BaseJobSource. Una fuente que falla NO puede romper el
resto del pipeline: el runner captura toda excepción y la registra en SourceLog.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class SourceKind:
    ATS = "ats"
    BOARD = "board"
    AGGREGATOR = "aggregator"
    CAREERS = "careers"


class ComplianceLevel:
    """Orden de preferencia del §8."""

    OFFICIAL_API = "official_api"
    PUBLIC_ATS_API = "public_ats_api"
    RSS_FEED = "rss_feed"
    USER_INBOX = "user_inbox"   # el sitio le envía los avisos por mail a la usuaria
    PUBLIC_HTML = "public_html"
    RESTRICTED = "restricted"  # requiere acuerdo/credenciales; deshabilitado por defecto


@dataclass
class RawJob:
    """Aviso tal como lo devuelve una fuente, antes de normalizar."""

    source: str
    source_job_id: str
    url: str
    title: str
    company: str
    location: str | None = None
    description: str | None = None
    apply_url: str | None = None
    employment_type: str | None = None
    remote_hint: str | None = None
    seniority_hint: str | None = None
    published_at: datetime | None = None
    deadline: datetime | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    department: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    source: str
    target: str | None
    jobs: list[RawJob]
    status: str = "ok"           # ok | error | skipped
    http_status: int | None = None
    error: str | None = None
    duration_ms: int = 0


@dataclass
class SourceTarget:
    """Un objetivo concreto dentro de una fuente (una empresa, una query)."""

    key: str
    label: str
    params: dict[str, Any] = field(default_factory=dict)


class BaseJobSource(ABC):
    key: str = "base"
    label: str = "Base"
    kind: str = SourceKind.ATS
    compliance: str = ComplianceLevel.PUBLIC_ATS_API
    compliance_note: str = ""
    enabled_by_default: bool = True
    requires_config: bool = False

    def __init__(self, client: httpx.AsyncClient | None = None, config: dict | None = None):
        self._client = client
        self._owns_client = client is None
        self.config = config or {}

    # ---------------- ciclo de vida ---------------- #
    async def __aenter__(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.http_timeout_seconds,
                headers={"User-Agent": settings.http_user_agent, "Accept": "application/json"},
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, *exc):
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(f"{self.key}: usar dentro de 'async with'")
        return self._client

    # ---------------- contrato ---------------- #
    @abstractmethod
    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        """Devuelve avisos crudos para un objetivo."""

    async def fetch_job(self, raw: RawJob) -> RawJob:
        """Enriquece un aviso (descripción completa). Por defecto no hace nada."""
        return raw

    @abstractmethod
    def normalize_job(self, raw: RawJob) -> RawJob:
        """Limpieza específica de la fuente antes del normalizador global."""

    async def health_check(self) -> tuple[bool, str]:
        """Chequeo liviano de disponibilidad."""
        try:
            targets = self.default_targets()
            if not targets:
                return True, "sin objetivos configurados"
            jobs = await self.search_jobs(targets[0])
            return True, f"{len(jobs)} avisos en {targets[0].label}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    def default_targets(self) -> list[SourceTarget]:
        return []

    # ---------------- helpers ---------------- #
    async def _get_json(self, url: str, **kwargs) -> Any:
        await asyncio.sleep(settings.source_rate_limit_seconds)
        resp = await self.client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def _get_text(self, url: str, **kwargs) -> str:
        await asyncio.sleep(settings.source_rate_limit_seconds)
        resp = await self.client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text

    async def run(self, target: SourceTarget) -> FetchResult:
        """Ejecuta un objetivo aislando errores."""
        started = datetime.now()
        try:
            jobs = await self.search_jobs(target)
            jobs = [self.normalize_job(j) for j in jobs]
            ms = int((datetime.now() - started).total_seconds() * 1000)
            return FetchResult(self.key, target.label, jobs, "ok", 200, None, ms)
        except httpx.HTTPStatusError as exc:
            ms = int((datetime.now() - started).total_seconds() * 1000)
            logger.warning("source=%s target=%s http_error=%s", self.key, target.key, exc.response.status_code)
            return FetchResult(self.key, target.label, [], "error", exc.response.status_code, str(exc)[:500], ms)
        except Exception as exc:  # noqa: BLE001
            ms = int((datetime.now() - started).total_seconds() * 1000)
            logger.warning("source=%s target=%s error=%s", self.key, target.key, exc)
            return FetchResult(self.key, target.label, [], "error", None, f"{type(exc).__name__}: {exc}"[:500], ms)
