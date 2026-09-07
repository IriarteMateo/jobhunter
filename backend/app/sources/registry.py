"""Registro central de fuentes y armado de objetivos (§35, §36)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, JobSource, TargetCompany
from app.sources.aggregators import (
    ArbeitnowSource,
    HimalayasSource,
    JobicySource,
    RemotiveSource,
)
from app.sources.ats import (
    AshbySource,
    GreenhouseSource,
    LeverSource,
    RecruiteeSource,
    SmartRecruitersSource,
    WorkableSource,
)
from app.sources.base import BaseJobSource, SourceTarget
from app.sources.careers import CompanyCareerSource, SuccessFactorsSource
from app.sources.email_alerts import EmailAlertsSource
from app.sources.enterprise import (
    AmazonJobsSource,
    EightfoldSource,
    OracleRecruitingSource,
    PhenomSource,
)
from app.sources.restricted import (
    BumeranSource,
    GlassdoorSource,
    IndeedSource,
    LinkedInSource,
    SavedSearchLinksSource,
    ZonaJobsSource,
)
from app.sources.workday import WorkdaySource

SOURCE_CLASSES: dict[str, type[BaseJobSource]] = {
    c.key: c
    for c in (
        GreenhouseSource,
        LeverSource,
        AshbySource,
        SmartRecruitersSource,
        WorkableSource,
        RecruiteeSource,
        WorkdaySource,
        OracleRecruitingSource,
        EightfoldSource,
        AmazonJobsSource,
        PhenomSource,
        SuccessFactorsSource,
        CompanyCareerSource,
        EmailAlertsSource,
        RemotiveSource,
        ArbeitnowSource,
        JobicySource,
        HimalayasSource,
        LinkedInSource,
        IndeedSource,
        BumeranSource,
        ZonaJobsSource,
        GlassdoorSource,
        SavedSearchLinksSource,
    )
}

# Fuentes por-empresa: los objetivos salen de target_companies
COMPANY_DRIVEN = {
    "greenhouse", "lever", "ashby", "smartrecruiters", "workable",
    "recruitee", "workday", "successfactors", "company_careers",
    "oracle_recruiting", "eightfold", "amazon_jobs", "phenom",
}


def sync_source_catalog(db: Session) -> None:
    """Asegura una fila en job_sources por cada adaptador registrado."""
    existing = {s.key: s for s in db.scalars(select(JobSource))}
    for key, cls in SOURCE_CLASSES.items():
        row = existing.get(key)
        if row is None:
            db.add(
                JobSource(
                    key=key,
                    label=cls.label,
                    kind=cls.kind,
                    enabled=cls.enabled_by_default,
                    requires_config=cls.requires_config,
                    compliance_note=cls.compliance_note,
                )
            )
        else:
            row.label = cls.label
            row.kind = cls.kind
            row.requires_config = cls.requires_config
            row.compliance_note = cls.compliance_note
    db.commit()


def enabled_source_keys(db: Session) -> set[str]:
    return {s.key for s in db.scalars(select(JobSource)) if s.enabled}


def build_plan(db: Session, only: list[str] | None = None) -> list[tuple[str, SourceTarget]]:
    """Devuelve [(source_key, target)] a ejecutar en esta corrida."""
    enabled = enabled_source_keys(db)
    if only:
        enabled &= set(only)

    plan: list[tuple[str, SourceTarget]] = []

    # 1) Fuentes agnósticas de empresa (agregadores)
    for key in sorted(enabled - COMPANY_DRIVEN):
        cls = SOURCE_CLASSES.get(key)
        if cls is None:
            continue
        for target in cls().default_targets():
            plan.append((key, target))

    # 2) Fuentes por empresa objetivo
    rows = db.execute(
        select(TargetCompany, Company).join(Company, TargetCompany.company_id == Company.id)
    ).all()
    for tc, company in rows:
        if not tc.enabled or tc.suggested or not tc.ats_type:
            continue
        if tc.ats_type not in enabled:
            continue
        params: dict = {"company": company.name}
        if tc.ats_type == "workday":
            cfg = (tc.careers_url or "").split("|")  # tenant|site|host
            if len(cfg) < 2:
                continue
            params |= {"tenant": cfg[0], "site": cfg[1], "host": cfg[2] if len(cfg) > 2 else "wd3",
                       "search_text": "Argentina"}
        elif tc.ats_type == "oracle_recruiting":
            cfg = (tc.careers_url or "").split("|")   # host|site
            if not cfg or not cfg[0]:
                continue
            params |= {"host": cfg[0], "site": cfg[1] if len(cfg) > 1 else "CX_1",
                       "location": "Argentina"}
        elif tc.ats_type == "eightfold":
            careers = tc.careers_url or ""
            # Un dominio propio (https://...) sirve la misma API en /api/positions
            if careers.startswith("http"):
                params |= {"base_url": careers, "location": "Argentina"}
            else:
                params |= {"token": tc.ats_token or "", "domain": careers,
                           "location": "Argentina"}
        elif tc.ats_type == "successfactors":
            params |= {"base_url": tc.careers_url or "", "location": "Argentina"}
        elif tc.ats_type == "phenom":
            params |= {"host": tc.careers_url or "", "location": "Argentina"}
        elif tc.ats_type == "amazon_jobs":
            params |= {"country": tc.ats_token or "ARG"}
        elif tc.ats_type == "company_careers":
            params |= {"url": tc.careers_url or ""}
        else:
            params |= {"token": tc.ats_token or ""}
            if tc.ats_type == "smartrecruiters":
                params |= {"country": "ar"}
        plan.append((tc.ats_type, SourceTarget(key=f"{tc.ats_type}:{tc.ats_token or company.normalized_name}",
                                               label=company.name, params=params)))
    return plan


def get_source(key: str, config: dict | None = None) -> BaseJobSource:
    cls = SOURCE_CLASSES[key]
    return cls(config=config)


__all__ = [
    "SOURCE_CLASSES",
    "COMPANY_DRIVEN",
    "sync_source_catalog",
    "build_plan",
    "get_source",
    "enabled_source_keys",
    "SavedSearchLinksSource",
]
