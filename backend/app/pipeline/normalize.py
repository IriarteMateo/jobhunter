"""Normalización de RawJob -> campos de Job (§9, §10)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.models import RemoteType, utcnow
from app.pipeline.dedupe import build_fingerprint
from app.pipeline.location import detect_remote_type
from app.pipeline.text import (
    clean_text,
    content_hash,
    description_hash,
    normalize_company,
    normalize_title,
)
from app.sources.base import RawJob

CURRENCY_PATTERNS = [
    (re.compile(r"(?:ars|\$)\s*([\d.,]{4,})", re.I), "ARS"),
    (re.compile(r"(?:usd|us\$|u\$s)\s*([\d.,]{3,})", re.I), "USD"),
    (re.compile(r"(?:eur|€)\s*([\d.,]{3,})", re.I), "EUR"),
]
RANGE_PATTERN = re.compile(
    r"([\d][\d.,]{2,})\s*(?:-|–|to|a|hasta)\s*([\d][\d.,]{2,})", re.I
)

EMPLOYMENT_MAP = {
    "full-time": "Full-time", "fulltime": "Full-time", "full time": "Full-time",
    "tiempo completo": "Full-time", "vollzeit": "Full-time", "permanent": "Full-time",
    "part-time": "Part-time", "part time": "Part-time", "medio tiempo": "Part-time",
    "teilzeit": "Part-time",
    "intern": "Internship", "internship": "Internship", "pasantia": "Internship",
    "praktikum": "Internship", "temporary": "Temporary", "contract": "Contract",
    "contrato": "Contract", "freelance": "Freelance", "trainee": "Trainee",
}


@dataclass
class NormalizedJob:
    job_id: str
    source: str
    source_job_id: str
    url: str
    apply_url: str | None
    job_title: str
    title_normalized: str
    company: str
    company_normalized: str
    location: str | None
    location_city: str | None
    location_country: str | None
    remote_type: str
    employment_type: str | None
    description: str | None
    description_hash: str | None
    publication_date: datetime | None
    application_deadline: datetime | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_is_published: bool
    fingerprint: str
    raw_payload: dict


def _parse_number(value: str) -> float | None:
    cleaned = value.replace(".", "").replace(" ", "")
    cleaned = cleaned.replace(",", ".") if cleaned.count(",") == 1 and len(cleaned.split(",")[-1]) == 2 else cleaned.replace(",", "")
    try:
        num = float(cleaned)
    except ValueError:
        return None
    return num if num >= 100 else None


def extract_salary(raw: RawJob) -> tuple[float | None, float | None, str | None, bool]:
    """Sólo devuelve salario si viene publicado (§45). Nunca lo estima."""
    if raw.salary_min or raw.salary_max:
        return raw.salary_min, raw.salary_max, raw.salary_currency, True

    text = " ".join(
        str(v) for v in (raw.raw.get("salary_text"), raw.raw.get("compensation_summary")) if v
    )
    if not text:
        return None, None, None, False

    currency = next((cur for pattern, cur in CURRENCY_PATTERNS if pattern.search(text)), None)
    match = RANGE_PATTERN.search(text)
    if match:
        lo, hi = _parse_number(match.group(1)), _parse_number(match.group(2))
        if lo or hi:
            return lo, hi, currency, True
    for pattern, cur in CURRENCY_PATTERNS:
        m = pattern.search(text)
        if m:
            value = _parse_number(m.group(1))
            if value:
                return value, None, cur, True
    return None, None, None, False


def split_location(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    parts = [clean_text(p) for p in location.split(",") if clean_text(p)]
    if not parts:
        return None, None
    city = parts[0]
    country = parts[-1] if len(parts) > 1 else None
    return city, country


def normalize_employment_type(value: str | None) -> str | None:
    if not value:
        return None
    low = value.strip().lower()
    for key, label in EMPLOYMENT_MAP.items():
        if key in low:
            return label
    return clean_text(value).title()[:64]


def normalize(raw: RawJob) -> NormalizedJob:
    title = clean_text(raw.title)
    company = clean_text(raw.company) or "Empresa no identificada"
    description = raw.description.strip() if raw.description else None
    remote_type = detect_remote_type(raw.location, description, raw.remote_hint, title)
    city, country = split_location(raw.location)
    salary_min, salary_max, currency, published = extract_salary(raw)

    return NormalizedJob(
        job_id=content_hash(raw.source, raw.source_job_id, raw.url),
        source=raw.source,
        source_job_id=str(raw.source_job_id),
        url=raw.url,
        apply_url=raw.apply_url or raw.url,
        job_title=title,
        title_normalized=normalize_title(title),
        company=company,
        company_normalized=normalize_company(company),
        location=clean_text(raw.location) or None,
        location_city=city,
        location_country=country,
        remote_type=remote_type.value if isinstance(remote_type, RemoteType) else str(remote_type),
        employment_type=normalize_employment_type(raw.employment_type),
        description=description,
        description_hash=description_hash(description) if description else None,
        publication_date=raw.published_at,
        application_deadline=raw.deadline,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency or raw.salary_currency,
        salary_is_published=published,
        fingerprint=build_fingerprint(company, title, raw.location),
        raw_payload={**{k: v for k, v in (raw.raw or {}).items() if k != "description"},
                     "seniority_hint": raw.seniority_hint},
    )


def is_stale(publication_date: datetime | None, max_age_days: int = 120) -> bool:
    if not publication_date:
        return False
    return (utcnow() - publication_date).days > max_age_days
