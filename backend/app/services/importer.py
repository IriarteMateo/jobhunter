"""Importación manual de un aviso (§8, complemento de las fuentes automáticas).

Sirve para todo lo que el pipeline no puede alcanzar solo: un aviso que le pasó
un contacto, un posteo de LinkedIn, un mensaje de WhatsApp, una búsqueda que
encontró navegando. Se pega el texto (o el link) y el aviso entra por el mismo
camino que cualquier otro: normalización, deduplicación y scoring completo.

Para dominios que prohíben el acceso automatizado NO se descarga la página: se
pide el texto pegado. Traer una URL que la usuaria acaba de pedir explícitamente
es distinto de recorrer un sitio, pero sólo se hace donde está permitido y
respetando robots.txt.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Job, JobSourceOccurrence, JobState, JobStatus, utcnow
from app.pipeline.dedupe import find_duplicate, merge_into
from app.pipeline.normalize import normalize
from app.services.companies import get_or_create_company
from app.services.profile import get_user
from app.sources.ats import html_to_text
from app.sources.base import RawJob
from app.sources.careers import CompanyCareerSource
from app.sources.compliance import is_allowed

logger = logging.getLogger(__name__)

# Dominios cuyos términos prohíben el acceso automatizado: no se descargan.
NO_FETCH_DOMAINS = (
    "linkedin.com", "indeed.com", "bumeran.com", "zonajobs.com",
    "glassdoor.com", "computrabajo.com",
)


# URLs de ATS conocidos: en vez de raspar el HTML se consulta su API pública,
# que devuelve el aviso estructurado y completo.
ATS_URL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("greenhouse", re.compile(
        r"(?:job-)?boards\.greenhouse\.io/(?P<token>[\w.-]+)/jobs/(?P<id>\d+)", re.I)),
    ("greenhouse", re.compile(
        r"greenhouse\.io/embed/job_app\?for=(?P<token>[\w.-]+)&(?:amp;)?token=(?P<id>\d+)", re.I)),
    ("lever", re.compile(
        r"jobs\.(?:eu\.)?lever\.co/(?P<token>[\w.-]+)/(?P<id>[0-9a-f-]{16,})", re.I)),
    ("ashby", re.compile(
        r"jobs\.ashbyhq\.com/(?P<token>[\w.-]+)/(?P<id>[0-9a-f-]{16,})", re.I)),
    ("smartrecruiters", re.compile(
        r"jobs\.smartrecruiters\.com/(?P<token>[\w.-]+)/(?P<id>\d+)", re.I)),
]


def detect_ats(url: str) -> tuple[str, str, str] | None:
    """(ats, token, job_id) si la URL es de un ATS con API pública."""
    for ats, pattern in ATS_URL_PATTERNS:
        match = pattern.search(url)
        if match:
            return ats, match.group("token"), match.group("id")
    return None


async def fetch_from_ats(ats: str, token: str, job_id: str) -> RawJob | None:
    """Trae el aviso desde la API pública del ATS."""
    from app.sources.ats import (
        AshbySource,
        GreenhouseSource,
        LeverSource,
        SmartRecruitersSource,
    )
    from app.sources.base import SourceTarget

    classes = {"greenhouse": GreenhouseSource, "lever": LeverSource,
               "ashby": AshbySource, "smartrecruiters": SmartRecruitersSource}
    source = classes[ats]()
    async with source:
        if ats == "greenhouse":
            data = await source._get_json(
                f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}"
            )
            from app.sources.ats import html_to_text as _to_text
            from app.sources.ats import parse_dt as _dt

            return RawJob(
                source="manual_import", source_job_id=f"greenhouse:{job_id}",
                url=data.get("absolute_url", ""), apply_url=data.get("absolute_url"),
                title=data.get("title", ""), company=data.get("company_name") or token,
                location=(data.get("location") or {}).get("name"),
                description=_to_text(data.get("content")),
                published_at=_dt(data.get("first_published") or data.get("updated_at")),
                raw={"imported": True, "ats": ats},
            )
        if ats == "lever":
            data = await source._get_json(f"https://api.lever.co/v0/postings/{token}/{job_id}")
            jobs = source.normalize_job  # reutiliza la limpieza del adaptador
            from app.sources.ats import html_to_text as _to_text
            from app.sources.ats import parse_dt as _dt

            categories = data.get("categories") or {}
            return jobs(RawJob(
                source="manual_import", source_job_id=f"lever:{job_id}",
                url=data.get("hostedUrl", ""), apply_url=data.get("applyUrl"),
                title=data.get("text", ""), company=token,
                location=categories.get("location"),
                description=_to_text(data.get("descriptionPlain") or data.get("description")),
                published_at=_dt(data.get("createdAt")),
                raw={"imported": True, "ats": ats},
            ))
        # Ashby y SmartRecruiters: se busca el aviso dentro del board
        target = SourceTarget(token, token, {"token": token, "company": token,
                                             "country": "ar"} if ats == "smartrecruiters"
                              else {"token": token, "company": token})
        for candidate in await source.search_jobs(target):
            if candidate.source_job_id == job_id or job_id in (candidate.url or ""):
                candidate.source = "manual_import"
                candidate.source_job_id = f"{ats}:{job_id}"
                candidate.raw = {"imported": True, "ats": ats}
                return candidate
    return None


class ImportError_(ValueError):
    """Error de importación con mensaje para la usuaria."""


@dataclass
class ImportResult:
    job_id: int
    created: bool
    merged_with_existing: bool
    fetched_url: bool
    message: str


def _domain_blocked(url: str) -> bool:
    """Compara etiquetas de dominio completas.

    Un `endswith` simple deja pasar "bumeran.com.ar" cuando la regla dice
    "bumeran.com", y bloquearía "notlinkedin.com" por error.
    """
    host = (urlparse(url).netloc or "").lower().split(":")[0]
    padded = f".{host}."
    return any(f".{domain}." in padded for domain in NO_FETCH_DOMAINS)


async def _fetch_url(url: str) -> tuple[str | None, dict]:
    """Descarga una URL permitida y devuelve (texto, metadatos)."""
    if not await is_allowed(url):
        raise ImportError_(
            "El robots.txt del sitio no permite leer esa página automáticamente. "
            "Pegá el texto del aviso y lo analizo igual."
        )
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers={"User-Agent": settings.http_user_agent},
        follow_redirects=True,
    ) as client:
        response = await client.get(url)
    response.raise_for_status()
    html = response.text

    # Muchas career pages publican JSON-LD: si está, es la mejor fuente.
    source = CompanyCareerSource()
    structured = source._parse_jsonld(html, url, "")
    if structured:
        best = structured[0]
        return best.description, {
            "title": best.title, "company": best.company, "location": best.location,
            "published_at": best.published_at, "apply_url": best.apply_url,
        }
    return html_to_text(html), {}


# Un aviso real combina varias señales distintas; una página de portal de
# carreras tiene a lo sumo una ("apply", "careers"). Se exigen al menos dos
# grupos diferentes para aceptar una descarga como aviso.
_JOB_SIGNAL_GROUPS = [
    re.compile(r"(requisit|requirement|qualification|lo que buscamos|tu perfil|"
               r"anforderungen|dein profil)", re.I),
    re.compile(r"(responsabilidad|responsibilit|what you.ll do|tus tareas|"
               r"funciones|deine aufgaben|sobre el rol|about the role)", re.I),
    re.compile(r"(a[nñ]os de experiencia|years of experience|nivel de ingl|"
               r"english level|excluyente|deseable|nice to have|preferred)", re.I),
    re.compile(r"(modalidad|jornada|full[- ]?time|part[- ]?time|h[ií]brid|"
               r"presencial|remoto|remote)", re.I),
    re.compile(r"(beneficios|benefits|ofrecemos|we offer|obra social|"
               r"prepaga|vacaciones)", re.I),
]

# Títulos que delatan una página de listado, no un puesto concreto
_PORTAL_TITLE = re.compile(
    r"(careers?|portal|jobs? at|join |trabaj[aá] con nosotros|oportunidades|"
    r"vacantes|openings|b[uú]squedas|our team|s[eé] parte)",
    re.I,
)


def _looks_like_a_posting(text: str, title: str) -> bool:
    if _PORTAL_TITLE.search(title or ""):
        return False
    matched = sum(1 for pattern in _JOB_SIGNAL_GROUPS if pattern.search(text or ""))
    return matched >= 2


def _guess_title(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if 6 <= len(line) <= 120:
            return line
    return "Aviso importado"


async def build_raw_job(*, url: str | None, text: str | None, title: str | None,
                        company: str | None, location: str | None) -> tuple[RawJob, bool]:
    """Arma el RawJob a importar. Devuelve (aviso, se_descargó_la_url)."""
    if not url and not text:
        raise ImportError_("Necesito el texto del aviso o su link.")

    description = (text or "").strip() or None
    meta: dict = {}
    fetched = False

    if url and not description:
        ats = detect_ats(url)
        if ats:
            raw = await fetch_from_ats(*ats)
            if raw is not None and raw.title:
                if location:
                    raw.location = location
                return raw, True
            raise ImportError_(
                "Ese aviso ya no figura en el board de la empresa (puede estar cerrado). "
                "Si lo tenés a mano, pegá el texto."
            )
        if _domain_blocked(url):
            raise ImportError_(
                f"{urlparse(url).netloc} no permite lectura automatizada. "
                "Abrí el aviso, copiá el texto y pegalo acá: se analiza igual y queda "
                "guardado con el link para postularte."
            )
        description, meta = await _fetch_url(url)
        fetched = True
        if not description or len(description) < 80:
            raise ImportError_(
                "No pude extraer contenido útil de esa página. Pegá el texto del aviso."
            )

    final_title = (title or meta.get("title") or _guess_title(description or "")).strip()
    final_company = (company or meta.get("company") or "").strip() or "Empresa no identificada"

    # Guardia: si se descargó una página y no salió nada que parezca un aviso,
    # es mejor pedir el texto que guardar un registro basura.
    if fetched and not (title or meta.get("title")):
        if not _looks_like_a_posting(description or "", final_title):
            raise ImportError_(
                "Esa página no parece el detalle de un aviso (puede ser un listado o "
                "cargar el contenido con JavaScript). Abrila, copiá el texto del puesto "
                "y pegalo acá."
            )
    final_location = (location or meta.get("location") or "").strip() or None

    identifier = url or f"{final_company}|{final_title}"
    raw = RawJob(
        source="manual_import",
        source_job_id=re.sub(r"\W+", "-", identifier.lower())[:180],
        url=url or "",
        apply_url=meta.get("apply_url") or url,
        title=final_title,
        company=final_company,
        location=final_location,
        description=description,
        published_at=meta.get("published_at"),
        raw={"imported": True, "fetched": fetched},
    )
    return raw, fetched


def persist_imported(db: Session, raw: RawJob) -> tuple[Job, bool, bool]:
    """Guarda el aviso importado deduplicando contra lo que ya existe."""
    norm = normalize(raw)

    existing_occurrence = db.scalars(
        select(JobSourceOccurrence).where(
            JobSourceOccurrence.source == norm.source,
            JobSourceOccurrence.source_job_id == norm.source_job_id,
        )
    ).first()
    if existing_occurrence:
        job = db.get(Job, existing_occurrence.job_id)
        if job:
            job.last_seen_date = utcnow()
            if norm.description and len(norm.description) > len(job.description or ""):
                job.description = norm.description
            return job, False, False

    decision = find_duplicate(
        db, company=norm.company, title=norm.job_title, location=norm.location,
        description_hash=norm.description_hash, fingerprint=norm.fingerprint,
    )
    if decision.action == "duplicate" and decision.existing is not None:
        job = decision.existing
        # Una importación manual trae la descripción completa que a una alerta
        # de email le falta: aprovecharla mejora el análisis del aviso existente.
        merge_into(job, source=norm.source, url=norm.url or job.url,
                   apply_url=norm.apply_url, description=norm.description,
                   publication_date=norm.publication_date)
        db.add(JobSourceOccurrence(job_id=job.id, source=norm.source,
                                   source_job_id=norm.source_job_id, url=norm.url or job.url))
        db.flush()
        return job, False, True

    company = get_or_create_company(db, norm.company)
    job = Job(
        job_id=norm.job_id, source=norm.source, source_job_id=norm.source_job_id,
        url=norm.url or (norm.apply_url or ""), apply_url=norm.apply_url,
        job_title=norm.job_title, title_normalized=norm.title_normalized,
        company=norm.company, company_normalized=norm.company_normalized,
        company_id=company.id, location=norm.location, location_city=norm.location_city,
        location_country=norm.location_country, remote_type=norm.remote_type,
        employment_type=norm.employment_type, description=norm.description,
        description_hash=norm.description_hash, publication_date=norm.publication_date,
        application_deadline=norm.application_deadline, salary_min=norm.salary_min,
        salary_max=norm.salary_max, salary_currency=norm.salary_currency,
        salary_is_published=norm.salary_is_published, fingerprint=norm.fingerprint,
        raw_payload=norm.raw_payload,
    )
    db.add(job)
    db.flush()
    db.add(JobSourceOccurrence(job_id=job.id, source=norm.source,
                               source_job_id=norm.source_job_id, url=job.url))
    user = get_user(db)
    db.add(JobState(user_id=user.id, job_id=job.id, status=JobStatus.NEW.value))
    db.flush()
    return job, True, False


async def import_job(db: Session, *, url: str | None = None, text: str | None = None,
                     title: str | None = None, company: str | None = None,
                     location: str | None = None) -> ImportResult:
    from app.pipeline.runner import RunSummary, _analyze

    raw, fetched = await build_raw_job(url=url, text=text, title=title,
                                       company=company, location=location)
    job, created, merged = persist_imported(db, raw)

    # Forzar el reanálisis: el contenido cambió respecto de lo cacheado
    if job.analysis:
        job.analysis.analysis_input_hash = None
    db.flush()
    await _analyze(db, [job], RunSummary(run_id=0))
    db.commit()

    if merged:
        message = "Ya tenía este puesto: se enriqueció con el texto que pegaste."
    elif created:
        message = "Aviso importado y analizado."
    else:
        message = "Este aviso ya estaba importado: se actualizó."
    return ImportResult(job_id=job.id, created=created, merged_with_existing=merged,
                        fetched_url=fetched, message=message)
