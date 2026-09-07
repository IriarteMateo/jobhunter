"""Armado de las tarjetas de empleo que consume el frontend."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    CompanyScore,
    Job,
    JobAnalysis,
    JobSourceOccurrence,
    JobState,
    JobStatus,
    TargetCompany,
    utcnow,
)
from app.pipeline.experience import ExperienceRequirement, experience_bucket
from app.pipeline.roles import match_role
from app.pipeline.scoring import category_for
from app.pipeline.summarize import summarize_description
from app.schemas import AnalysisOut, JobCard, JobDetail


def _experience_label(job: Job) -> str:
    req = ExperienceRequirement(
        min_years=job.experience_min,
        max_years=job.experience_max,
        is_hard=job.experience_is_hard_requirement,
        accepts_no_experience=(job.experience_min is not None and job.experience_min <= 0),
    )
    return experience_bucket(req)


def _company_meta(db: Session, job: Job) -> tuple[str, bool]:
    if not job.company_id:
        return "LOW", False
    score = db.scalars(
        select(CompanyScore).where(CompanyScore.company_id == job.company_id)
    ).first()
    target = db.scalars(
        select(TargetCompany).where(TargetCompany.company_id == job.company_id)
    ).first()
    return (score.confidence if score else "LOW",
            bool(target and target.enabled and not target.suggested))


def to_card(db: Session, job: Job, analysis: JobAnalysis | None,
            state: JobState | None) -> JobCard:
    confidence, is_target = _company_meta(db, job)
    emoji, label = category_for(analysis.recommendation) if analysis else ("⚪", "SIN ANALIZAR")
    sources = [o.source for o in job.occurrences] or [job.source]
    role = match_role(job.job_title, (job.description or "")[:1500])

    return JobCard(
        id=job.id,
        job_id=job.job_id,
        job_title=job.job_title,
        company=job.company,
        company_logo=(job.company_rel.logo_url if job.company_rel else None),
        company_quality_confidence=confidence,
        is_target_company=is_target,
        location=job.location,
        remote_type=job.remote_type,
        employment_type=job.employment_type,
        seniority=job.seniority,
        experience_label=_experience_label(job),
        languages=job.languages or [],
        skills=job.skills or [],
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        salary_is_published=job.salary_is_published,
        source=job.source,
        sources=sorted(set(sources)),
        url=job.url,
        apply_url=job.apply_url or job.url,
        publication_date=job.publication_date,
        first_seen_date=job.first_seen_date,
        is_new_today=(utcnow() - job.first_seen_date) < timedelta(hours=24),
        is_repost=job.is_repost,
        status=state.status if state else JobStatus.NEW.value,
        category_emoji=emoji,
        category_label=label,
        role_family=role.family_label,
        analysis=AnalysisOut.model_validate(analysis) if analysis else None,
    )


def to_detail(db: Session, job: Job, analysis: JobAnalysis | None,
              state: JobState | None) -> JobDetail:
    card = to_card(db, job, analysis, state)
    application = None
    if state:
        app_row = db.scalars(
            select(Application).where(Application.state_id == state.id)
        ).first()
        if app_row:
            application = {
                "applied_at": app_row.applied_at,
                "stage": app_row.stage,
                "notes": app_row.notes,
                "recruiter_contact": app_row.recruiter_contact,
                "next_interview_at": app_row.next_interview_at,
                "expected_salary": app_row.expected_salary,
                "outcome": app_row.outcome,
            }
    occurrences = [
        {"source": o.source, "url": o.url, "first_seen_at": o.first_seen_at}
        for o in db.scalars(
            select(JobSourceOccurrence).where(JobSourceOccurrence.job_id == job.id)
        )
    ]
    digest = summarize_description(job.description)
    return JobDetail(
        **card.model_dump(),
        description=job.description,
        resumen=digest.to_dict() if digest.tiene_contenido else None,
        requirements=job.requirements or [],
        preferred_requirements=job.preferred_requirements or [],
        education_requirements=job.education_requirements or [],
        application_deadline=job.application_deadline,
        occurrences=occurrences,
        application=application,
    )
