"""Empleos: listado con filtros, detalle, estados y feedback (§23, §24, §27)."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, nullslast, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Application,
    Job,
    JobAnalysis,
    JobState,
    JobStatus,
    Recommendation,
    TargetCompany,
    utcnow,
)
from app.schemas import JobDetail, JobImportIn, JobImportOut, JobListOut, StatusUpdate
from app.services import feedback as feedback_service
from app.services.profile import get_preference, get_user
from app.services.serialize import to_card, to_detail

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

STATUS_FIELDS = {
    JobStatus.SAVED.value: "saved_at",
    JobStatus.DISCARDED.value: "dismissed_at",
    JobStatus.SEEN.value: "seen_at",
}
FEEDBACK_BY_STATUS = {
    JobStatus.SAVED.value: "interested",
    JobStatus.APPLIED.value: "applied",
    JobStatus.DISCARDED.value: "dismissed",
    JobStatus.REJECTED.value: "not_interested",
}


@router.get("", response_model=JobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    q: str | None = None,
    status: list[str] | None = Query(None),
    company: str | None = None,
    company_id: int | None = None,
    seniority: list[str] | None = Query(None),
    role_family: str | None = None,
    remote_type: list[str] | None = Query(None),
    location: str | None = None,
    min_score: float | None = None,
    min_company_score: float | None = None,
    min_career_score: float | None = None,
    german_only: bool = False,
    target_only: bool = False,
    graduate_only: bool = False,
    internship_only: bool = False,
    new_only: bool = False,
    include_not_eligible: bool = False,
    max_experience: float | None = None,
    days: int | None = None,
    order_by: str = "final_score",
    order_dir: str = "desc",
    page: int = 1,
    page_size: int = 30,
):
    user = get_user(db)
    display = get_preference(db, "display")
    threshold = min_score if min_score is not None else float(display.get("min_display_score", 70.0))

    stmt = (
        select(Job, JobAnalysis, JobState)
        .join(JobAnalysis, JobAnalysis.job_id == Job.id)
        .outerjoin(JobState, (JobState.job_id == Job.id) & (JobState.user_id == user.id))
        .where(Job.is_duplicate.is_(False))
    )

    if not include_not_eligible and display.get("hide_not_eligible", True):
        stmt = stmt.where(JobAnalysis.eligible.is_(True))
    stmt = stmt.where(JobAnalysis.final_score >= threshold)

    if status:
        stmt = stmt.where(JobState.status.in_(status))
    elif display.get("hide_dismissed", True):
        stmt = stmt.where(or_(JobState.status.is_(None),
                              JobState.status != JobStatus.DISCARDED.value))

    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Job.job_title).like(like),
                              func.lower(Job.company).like(like),
                              func.lower(Job.description).like(like)))
    if company:
        stmt = stmt.where(func.lower(Job.company).like(f"%{company.lower()}%"))
    if company_id is not None:
        stmt = stmt.where(Job.company_id == company_id)
    if seniority:
        stmt = stmt.where(Job.seniority.in_(seniority))
    if remote_type:
        stmt = stmt.where(Job.remote_type.in_(remote_type))
    if location:
        stmt = stmt.where(func.lower(Job.location).like(f"%{location.lower()}%"))
    if min_company_score is not None:
        stmt = stmt.where(JobAnalysis.company_quality_score >= min_company_score)
    if min_career_score is not None:
        stmt = stmt.where(JobAnalysis.career_value_score >= min_career_score)
    if german_only:
        stmt = stmt.where(JobAnalysis.german_advantage_score >= 50)
    if graduate_only:
        stmt = stmt.where(Job.seniority.in_(["Graduate", "Trainee"]))
    if internship_only:
        stmt = stmt.where(Job.seniority == "Internship")
    if max_experience is not None:
        stmt = stmt.where(or_(Job.experience_min.is_(None), Job.experience_min <= max_experience))
    if new_only:
        stmt = stmt.where(Job.first_seen_date >= utcnow() - timedelta(hours=24))
    if days:
        stmt = stmt.where(Job.first_seen_date >= utcnow() - timedelta(days=days))
    if target_only:
        target_ids = select(TargetCompany.company_id).where(
            TargetCompany.enabled.is_(True), TargetCompany.suggested.is_(False)
        )
        stmt = stmt.where(Job.company_id.in_(target_ids))

    # Muchos avisos no traen fecha de publicación: van al final en cualquier
    # dirección, si no ensucian el tope de la lista al ordenar por antigüedad.
    stmt = stmt.order_by(nullslast(_orden(order_by, order_dir)),
                         JobAnalysis.final_score.desc())

    rows = db.execute(stmt).all()
    if role_family:
        rows = [r for r in rows if _family_of(db, r[0]) == role_family]

    total = len(rows)
    start = max(0, (page - 1) * page_size)
    page_rows = rows[start: start + page_size]
    return JobListOut(
        total=total, page=page, page_size=page_size,
        items=[to_card(db, job, analysis, state) for job, analysis, state in page_rows],
    )


ORDER_COLUMNS = {
    "final_score": JobAnalysis.final_score,
    "fit_score": JobAnalysis.fit_score,
    "company_score": JobAnalysis.company_quality_score,
    "career_score": JobAnalysis.career_value_score,
    "german": JobAnalysis.german_advantage_score,
    "date": Job.first_seen_date,
    # Muchas fuentes no informan la fecha de publicación —SuccessFactors no la
    # expone en ninguno de sus avisos— y ordenar por una columna toda en nulo
    # dejaba la lista en el orden del desempate (puntaje), que parece un bug.
    # Se usa la fecha de descubrimiento como respaldo: es lo mismo que ya muestra
    # la tarjeta cuando dice "Encontrado hace 2 h" en vez de "Publicado hace…".
    "published": func.coalesce(Job.publication_date, Job.first_seen_date),
}


def _orden(order_by: str, order_dir: str):
    """Columna y dirección de orden, compartidas por el listado y Top Picks."""
    columna = ORDER_COLUMNS.get(order_by, JobAnalysis.final_score)
    return columna.asc() if order_dir.lower() == "asc" else columna.desc()


def _family_of(db: Session, job: Job) -> str | None:
    from app.pipeline.roles import match_role

    return match_role(job.job_title, (job.description or "")[:1200]).family


@router.get("/top-picks")
def top_picks(db: Session = Depends(get_db), limit: int = 6,
              order_by: str = "final_score", order_dir: str = "desc"):
    """Las mejores oportunidades agrupadas por categoría (§25)."""
    user = get_user(db)
    threshold = float(get_preference(db, "display").get("min_display_score", 70.0))
    rows = db.execute(
        select(Job, JobAnalysis, JobState)
        .join(JobAnalysis, JobAnalysis.job_id == Job.id)
        .outerjoin(JobState, (JobState.job_id == Job.id) & (JobState.user_id == user.id))
        .where(Job.is_duplicate.is_(False), JobAnalysis.eligible.is_(True),
               JobAnalysis.final_score >= threshold)
        .order_by(nullslast(_orden(order_by, order_dir)), JobAnalysis.final_score.desc())
    ).all()
    rows = [r for r in rows if not (r[2] and r[2].status == JobStatus.DISCARDED.value)]

    target_ids = {t.company_id for t in db.scalars(
        select(TargetCompany).where(TargetCompany.enabled.is_(True),
                                    TargetCompany.suggested.is_(False))
    )}
    families = {job.id: _family_of(db, job) for job, _, _ in rows}

    buckets = [
        ("aplicar_hoy", "🔥 Aplicar hoy",
         lambda j, a: a.recommendation == Recommendation.APPLY_NOW.value),
        ("empresas_sonadas", "⭐ Empresas soñadas",
         lambda j, a: j.company_id in target_ids and a.company_quality_score >= 80),
        ("aleman", "🇩🇪 Alemán como ventaja", lambda j, a: a.german_advantage_score >= 50),
        ("graduate", "🎓 Graduate / Entry Level",
         lambda j, a: j.seniority in ("Graduate", "Trainee", "Internship", "Entry Level")),
        ("product_tech", "💻 Product / Tech",
         lambda j, a: families.get(j.id) in ("product", "tech_business")),
        ("business", "📊 Business / Strategy",
         lambda j, a: families.get(j.id) in ("business", "consulting", "operations")),
        ("data", "📈 Data / Analytics", lambda j, a: families.get(j.id) == "data"),
        ("finance", "💰 Finance / Fintech", lambda j, a: families.get(j.id) == "finance"),
    ]
    out = []
    for key, label, predicate in buckets:
        items = [to_card(db, j, a, s) for j, a, s in rows if predicate(j, a)][:limit]
        out.append({"key": key, "label": label, "count": len(items), "items": items})
    return {"buckets": out}


@router.post("/import", response_model=JobImportOut)
async def import_job_endpoint(payload: JobImportIn, db: Session = Depends(get_db)):
    """Importa un aviso pegando su texto o su link, y lo analiza igual que al resto."""
    from app.services.importer import ImportError_, import_job

    try:
        result = await import_job(
            db, url=payload.url, text=payload.text, title=payload.title,
            company=payload.company, location=payload.location,
        )
    except ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc

    job = db.get(Job, result.job_id)
    analysis = db.scalars(select(JobAnalysis).where(JobAnalysis.job_id == job.id)).first()
    state = db.scalars(
        select(JobState).where(JobState.user_id == get_user(db).id, JobState.job_id == job.id)
    ).first()
    return JobImportOut(
        job_id=result.job_id, created=result.created,
        merged_with_existing=result.merged_with_existing, fetched_url=result.fetched_url,
        message=result.message, job=to_detail(db, job, analysis, state),
    )


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)):
    user = get_user(db)
    row = db.execute(
        select(Job, JobAnalysis, JobState)
        .outerjoin(JobAnalysis, JobAnalysis.job_id == Job.id)
        .outerjoin(JobState, (JobState.job_id == Job.id) & (JobState.user_id == user.id))
        .where(Job.id == job_id)
    ).first()
    if row is None:
        raise HTTPException(404, "empleo no encontrado")
    job, analysis, state = row

    # Verlo lo marca como visto (§43: no vuelve a aparecer como nuevo)
    if state is None:
        state = JobState(user_id=user.id, job_id=job.id, status=JobStatus.SEEN.value,
                         seen_at=utcnow())
        db.add(state)
    elif state.status == JobStatus.NEW.value:
        state.status = JobStatus.SEEN.value
        state.seen_at = utcnow()
    db.commit()
    return to_detail(db, job, analysis, state)


@router.post("/{job_id}/status", response_model=JobDetail)
def set_status(job_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    user = get_user(db)
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "empleo no encontrado")
    try:
        status = JobStatus(payload.status)
    except ValueError:
        raise HTTPException(422, f"estado inválido: {payload.status}") from None

    state = db.scalars(
        select(JobState).where(JobState.user_id == user.id, JobState.job_id == job_id)
    ).first()
    if state is None:
        state = JobState(user_id=user.id, job_id=job_id)
        db.add(state)
        db.flush()

    state.status = status.value
    field = STATUS_FIELDS.get(status.value)
    if field:
        setattr(state, field, utcnow())
    if status == JobStatus.DISCARDED:
        state.dismiss_reason = payload.reason

    if status in (JobStatus.APPLIED, JobStatus.INTERVIEW, JobStatus.REJECTED):
        app_row = db.scalars(
            select(Application).where(Application.state_id == state.id)
        ).first()
        if app_row is None:
            app_row = Application(state_id=state.id, applied_at=utcnow())
            db.add(app_row)
        for attr in ("notes", "recruiter_contact", "stage", "next_interview_at",
                     "expected_salary"):
            value = getattr(payload, attr, None)
            if value is not None:
                setattr(app_row, attr, value)
        if status == JobStatus.REJECTED:
            app_row.outcome = "rejected"

    action = FEEDBACK_BY_STATUS.get(status.value)
    if action:
        from app.pipeline.roles import match_role

        role = match_role(job.job_title, (job.description or "")[:1200])
        feedback_service.record(
            db, job_id=job_id, action=action, reason=payload.reason,
            features={"role_family": role.family, "company": job.company_normalized,
                      "seniority": job.seniority, "remote_type": job.remote_type},
        )
    db.commit()

    analysis = db.scalars(select(JobAnalysis).where(JobAnalysis.job_id == job_id)).first()
    return to_detail(db, job, analysis, state)


@router.post("/{job_id}/feedback")
def send_feedback(job_id: int, action: str, reason: str | None = None,
                  db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "empleo no encontrado")
    from app.pipeline.roles import match_role

    role = match_role(job.job_title, (job.description or "")[:1200])
    feedback_service.record(db, job_id=job_id, action=action, reason=reason,
                            features={"role_family": role.family})
    db.commit()
    return {"ok": True, "personalizacion": feedback_service.explain(db)}
