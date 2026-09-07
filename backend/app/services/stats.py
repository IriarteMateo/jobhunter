"""Métricas del dashboard (§22, §28)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    Job,
    JobAnalysis,
    JobState,
    JobStatus,
    Recommendation,
    SearchRun,
    TargetCompany,
    utcnow,
)
from app.services.profile import get_preference, get_user

ACTIONABLE = {Recommendation.APPLY_NOW.value, Recommendation.STRONG.value,
              Recommendation.WORTH_IT.value}


def _threshold(db: Session) -> float:
    return float(get_preference(db, "display").get("min_display_score", 70.0))


def today_summary(db: Session) -> dict:
    """El bloque 'HOY' de la home."""
    user = get_user(db)
    threshold = _threshold(db)
    since = utcnow() - timedelta(hours=24)

    base = (
        select(Job, JobAnalysis, JobState)
        .join(JobAnalysis, JobAnalysis.job_id == Job.id)
        .join(JobState, (JobState.job_id == Job.id) & (JobState.user_id == user.id))
        .where(Job.is_duplicate.is_(False), Job.first_seen_date >= since)
    )
    rows = db.execute(base).all()
    analyzed_today = len(rows)
    relevant = [r for r in rows if r[1].final_score >= threshold and r[1].eligible]
    apply_now = [r for r in relevant if r[1].recommendation == Recommendation.APPLY_NOW.value]

    target_ids = {t.company_id for t in db.scalars(
        select(TargetCompany).where(TargetCompany.enabled.is_(True),
                                    TargetCompany.suggested.is_(False))
    )}
    from_targets = [r for r in relevant if r[0].company_id in target_ids]
    german = [r for r in relevant if r[1].german_advantage_score >= 50]

    last_run = db.scalars(select(SearchRun).order_by(SearchRun.started_at.desc())).first()
    return {
        "nuevas_hoy": analyzed_today,
        "recomendadas": len(relevant),
        "aplicar_ya": len(apply_now),
        "empresas_objetivo": len(from_targets),
        "con_aleman": len(german),
        "threshold": threshold,
        "ultima_corrida": {
            "id": last_run.id,
            "status": last_run.status,
            "finished_at": last_run.finished_at,
            "new_jobs": last_run.new_jobs,
            "raw_jobs": last_run.raw_jobs,
            "filtered_out": last_run.filtered_out,
            "duration_ms": last_run.duration_ms,
        } if last_run else None,
    }


def weekly_stats(db: Session) -> dict:
    user = get_user(db)
    threshold = _threshold(db)
    week_ago = utcnow() - timedelta(days=7)

    found_week = db.scalar(
        select(func.count(Job.id)).where(Job.first_seen_date >= week_ago,
                                         Job.is_duplicate.is_(False))
    ) or 0
    recommended_week = db.scalar(
        select(func.count(JobAnalysis.id))
        .join(Job, Job.id == JobAnalysis.job_id)
        .where(Job.first_seen_date >= week_ago, JobAnalysis.final_score >= threshold,
               JobAnalysis.eligible.is_(True))
    ) or 0
    applications = db.scalar(select(func.count(Application.id))) or 0
    interviews = db.scalar(
        select(func.count(JobState.id)).where(JobState.user_id == user.id,
                                              JobState.status == JobStatus.INTERVIEW.value)
    ) or 0
    saved = db.scalar(
        select(func.count(JobState.id)).where(JobState.user_id == user.id,
                                              JobState.status == JobStatus.SAVED.value)
    ) or 0
    dismissed = db.scalar(
        select(func.count(JobState.id)).where(JobState.user_id == user.id,
                                              JobState.status == JobStatus.DISCARDED.value)
    ) or 0
    avg_fit = db.scalar(select(func.avg(JobAnalysis.fit_score))) or 0.0
    german_count = db.scalar(
        select(func.count(JobAnalysis.id)).where(JobAnalysis.german_advantage_score >= 50)
    ) or 0

    top_companies = [
        {"company": name, "count": count}
        for name, count in db.execute(
            select(Job.company, func.count(Job.id))
            .join(JobAnalysis, JobAnalysis.job_id == Job.id)
            .where(JobAnalysis.final_score >= threshold)
            .group_by(Job.company).order_by(func.count(Job.id).desc()).limit(8)
        ).all()
    ]
    by_seniority = [
        {"seniority": s, "count": c}
        for s, c in db.execute(
            select(Job.seniority, func.count(Job.id))
            .group_by(Job.seniority).order_by(func.count(Job.id).desc())
        ).all()
    ]
    by_recommendation = [
        {"recommendation": r, "count": c}
        for r, c in db.execute(
            select(JobAnalysis.recommendation, func.count(JobAnalysis.id))
            .group_by(JobAnalysis.recommendation)
        ).all()
    ]
    return {
        "encontrados_semana": found_week,
        "recomendados_semana": recommended_week,
        "aplicaciones": applications,
        "entrevistas": interviews,
        "guardados": saved,
        "descartados": dismissed,
        "conversion_rate": round(100.0 * interviews / applications, 1) if applications else 0.0,
        "promedio_fit": round(float(avg_fit), 1),
        "ofertas_con_aleman": german_count,
        "top_empresas": top_companies,
        "por_seniority": by_seniority,
        "por_recomendacion": by_recommendation,
    }
