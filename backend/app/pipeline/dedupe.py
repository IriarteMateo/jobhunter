"""Deduplicación multi-fuente y detección de reposts (§10, §44).

Si un aviso está en LinkedIn y en la página oficial, se muestra UNA vez y el
apply_url apunta a la página oficial de la empresa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job, utcnow
from app.pipeline.text import content_hash, normalize_company, normalize_title

# Prioridad de fuente para elegir el apply_url canónico (§10)
SOURCE_PRIORITY = {
    "company_careers": 100,
    "greenhouse": 90,
    "lever": 90,
    "ashby": 90,
    "workday": 88,
    "smartrecruiters": 88,
    "successfactors": 86,
    "workable": 85,
    "recruitee": 85,
    "linkedin": 50,
    "indeed": 45,
    "bumeran": 45,
    "zonajobs": 45,
    "glassdoor": 40,
    "remotive": 35,
    "himalayas": 33,
    "jobicy": 32,
    "arbeitnow": 30,
}

TITLE_SIMILARITY_THRESHOLD = 88
REPOST_WINDOW_DAYS = 21


def source_priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, 20)


def location_bucket(location: str | None) -> str:
    """Agrupa ubicaciones equivalentes para el fingerprint."""
    from app.pipeline.text import searchable

    loc = searchable(location)
    if not loc:
        return "unknown"
    for key in ("remote", "remoto", "anywhere"):
        if key in loc:
            return "remote"
    for key in ("buenos aires", "caba", "capital federal", "argentina",
                "san isidro", "vicente lopez", "martinez", "olivos"):
        if key in loc:
            return "buenos-aires"
    return loc.split(",")[0].strip()[:40]


def build_fingerprint(company: str, title: str, location: str | None) -> str:
    return content_hash(
        normalize_company(company), normalize_title(title), location_bucket(location)
    )


@dataclass
class DedupeDecision:
    action: str              # "new" | "duplicate" | "same_source_update" | "repost"
    existing: Job | None = None
    reason: str | None = None
    similarity: float = 0.0


def find_duplicate(db: Session, *, company: str, title: str, location: str | None,
                   description_hash: str | None, fingerprint: str,
                   exclude_id: int | None = None) -> DedupeDecision:
    """Busca un empleo ya guardado que sea el mismo puesto."""
    # 1) Fingerprint exacto: misma empresa, mismo título normalizado, misma zona
    stmt = select(Job).where(Job.fingerprint == fingerprint, Job.is_duplicate.is_(False))
    if exclude_id:
        stmt = stmt.where(Job.id != exclude_id)
    hit = db.scalars(stmt).first()
    if hit:
        return DedupeDecision("duplicate", hit, "fingerprint idéntico", 100.0)

    # 2) Misma descripción exacta (aunque cambie el título)
    if description_hash:
        stmt = select(Job).where(
            Job.description_hash == description_hash, Job.is_duplicate.is_(False)
        )
        if exclude_id:
            stmt = stmt.where(Job.id != exclude_id)
        hit = db.scalars(stmt).first()
        if hit:
            return DedupeDecision("duplicate", hit, "descripción idéntica", 100.0)

    # 3) Misma empresa + título muy similar + misma zona
    comp = normalize_company(company)
    norm_title = normalize_title(title)
    bucket = location_bucket(location)
    stmt = select(Job).where(Job.company_normalized == comp, Job.is_duplicate.is_(False))
    if exclude_id:
        stmt = stmt.where(Job.id != exclude_id)
    for candidate in db.scalars(stmt).all():
        if location_bucket(candidate.location) != bucket:
            continue
        similarity = fuzz.token_set_ratio(norm_title, candidate.title_normalized)
        if similarity >= TITLE_SIMILARITY_THRESHOLD:
            return DedupeDecision("duplicate", candidate,
                                  f"título {similarity:.0f}% similar en la misma empresa y zona",
                                  float(similarity))
    return DedupeDecision("new")


def is_repost(existing: Job, new_publication_date) -> bool:
    """Republicación: mismo puesto y contenido, publicado de nuevo más tarde."""
    if not new_publication_date or not existing.publication_date:
        return False
    delta = new_publication_date - existing.publication_date
    return delta > timedelta(days=REPOST_WINDOW_DAYS)


def merge_into(existing: Job, *, source: str, url: str, apply_url: str | None,
               description: str | None, publication_date) -> bool:
    """Fusiona un duplicado en el registro canónico. True si mejoró el apply_url."""
    existing.last_seen_date = utcnow()
    improved = False
    if source_priority(source) > source_priority(existing.source):
        existing.original_source = existing.source
        existing.source = source
        existing.url = url
        existing.apply_url = apply_url or url
        improved = True
    elif not existing.apply_url and apply_url:
        existing.apply_url = apply_url
    if description and len(description) > len(existing.description or ""):
        existing.description = description
    if publication_date and (not existing.publication_date
                             or publication_date < existing.publication_date):
        existing.publication_date = publication_date
    return improved
