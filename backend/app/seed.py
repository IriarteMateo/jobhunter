"""Carga inicial: perfil de la candidata, empresas objetivo y catálogo de fuentes."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.target_companies import SEED_COMPANIES
from app.db import init_db, session_scope
from app.models import Company, TargetCompany
from app.services.companies import get_or_create_company
from app.services.profile import get_profile, get_user
from app.sources.registry import sync_source_catalog

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = dict(
    full_name="Candidata",
    headline="Licenciada en Negocios Digitales (UdeSA) · Español / Inglés / Alemán",
    university="Universidad de San Andrés (UdeSA)",
    degree="Licenciatura en Negocios Digitales",
    degree_field="Negocios Digitales",
    graduation_year=2025,
    education_extra=[
        {"institution": "Goethe-Schule", "detail": "Colegio alemán, bachillerato trilingüe"},
    ],
    languages=[
        {"code": "es", "name": "Español", "level": "Nativo"},
        {"code": "en", "name": "Inglés", "level": "C1 / Avanzado"},
        {"code": "de", "name": "Alemán", "level": "C1 / Avanzado"},
    ],
    years_experience=0.0,
    has_formal_experience=False,
    experience_items=[],
    skills=[
        "excel", "google sheets", "powerpoint", "notion", "canva",
        "google analytics", "power bi", "sql",
    ],
    target_roles=[
        "Business Analyst", "Product Analyst", "Strategy Analyst", "Operations Analyst",
        "Data Analyst", "Growth Analyst", "Consultant", "Graduate Program",
    ],
    role_families=["business", "product", "consulting", "data", "operations",
                   "marketing", "finance", "customer", "tech_business"],
    excluded_areas=["ventas puerta a puerta", "call center"],
    city="San Isidro",
    region="Zona Norte, Provincia de Buenos Aires",
    country="Argentina",
    accepts_remote=True,
    accepts_hybrid=True,
    accepts_onsite=True,
    max_commute_km=45,
    preferred_locations=[
        "San Isidro", "Martínez", "Vicente López", "Olivos", "Munro",
        "Acassuso", "Beccar", "Núñez", "Belgrano", "Palermo", "Retiro",
    ],
    salary_expectation_min=None,
    salary_currency="ARS",
    favorite_companies=[],
    blocked_companies=[],
)


def seed_profile(db: Session, overwrite: bool = False) -> None:
    profile = get_profile(db)
    if profile.university and not overwrite:
        return
    for key, value in DEFAULT_PROFILE.items():
        setattr(profile, key, value)
    db.flush()
    logger.info("perfil semilla cargado")


def seed_companies(db: Session) -> int:
    created = 0
    for item in SEED_COMPANIES:
        company = get_or_create_company(db, item["name"])
        company.notes = item.get("tier")           # tier curado (§15)
        company.size_bucket = item.get("size")
        company.website = company.website or item.get("careers_url")

        target = db.scalars(
            select(TargetCompany).where(TargetCompany.company_id == company.id)
        ).first()
        if target is None:
            target = TargetCompany(company_id=company.id)
            db.add(target)
            created += 1
        target.priority = item.get("priority", 2)
        target.category = item.get("category")
        target.german_relevant = item.get("german", False)
        target.ats_type = item.get("ats_type")
        target.ats_token = item.get("ats_token")
        target.careers_url = item.get("careers_url")
        target.enabled = True
        target.suggested = False
    db.flush()
    return created


def run_seed(overwrite_profile: bool = False) -> dict:
    init_db()
    with session_scope() as db:
        get_user(db)
        seed_profile(db, overwrite_profile)
        created = seed_companies(db)
        sync_source_catalog(db)
        total = db.scalar(select(Company.id).limit(1))
    return {"companies_created": created, "ok": bool(total is not None)}


if __name__ == "__main__":
    logging.basicConfig(level="INFO", format="%(levelname)s %(name)s: %(message)s")
    print(run_seed(overwrite_profile=True))
