"""Pipeline completo (§29).

FETCH -> PARSE -> NORMALIZE -> DEDUPE -> SENIORITY -> REQUIREMENTS ->
AI MATCHING -> COMPANY SCORING -> RANKING -> DB -> NOTIFICATIONS

Principio de aislamiento: cualquier fuente puede fallar sin afectar al resto.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import time
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.analyzer import analyze_deterministic, refine_with_llm, should_use_llm
from app.ai.providers import build_provider
from app.config import settings
from app.db import session_scope
from app.models import (
    Company,
    Job,
    JobAnalysis,
    JobSource,
    JobSourceOccurrence,
    JobState,
    JobStatus,
    Recommendation,
    SearchRun,
    SourceLog,
    utcnow,
)
from app.pipeline.dedupe import find_duplicate, is_repost, merge_into
from app.pipeline.normalize import normalize
from app.pipeline.prefilter import should_ingest
from app.pipeline.runlock import acquire as tomar_lock
from app.pipeline.runlock import release as soltar_lock
from app.services.companies import compute_company_quality, get_or_create_company, load_company_quality
from app.services.feedback import adjustments
from app.services.notifications import build_daily_digest, dispatch
from app.services.profile import (
    all_weights,
    build_context,
    get_preference,
    get_profile,
    get_user,
)
from app.sources.base import FetchResult, SourceTarget
from app.sources.registry import build_plan, get_source, sync_source_catalog

logger = logging.getLogger(__name__)


@dataclass
class RunSummary:
    run_id: int
    status: str = "ok"
    duration_ms: int = 0
    sources_queried: int = 0
    sources_failed: int = 0
    raw_jobs: int = 0
    new_jobs: int = 0
    updated_jobs: int = 0
    duplicates: int = 0
    reposts: int = 0
    filtered_out: int = 0
    analyzed_llm: int = 0
    analyzed_heuristic: int = 0
    recommended: int = 0
    errors: list[dict] = field(default_factory=list)
    source_results: list[dict] = field(default_factory=list)
    filter_reasons: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id, "status": self.status, "duration_ms": self.duration_ms,
            "sources_queried": self.sources_queried, "sources_failed": self.sources_failed,
            "raw_jobs": self.raw_jobs, "new_jobs": self.new_jobs,
            "updated_jobs": self.updated_jobs, "duplicates": self.duplicates,
            "reposts": self.reposts, "filtered_out": self.filtered_out,
            "analyzed_llm": self.analyzed_llm, "analyzed_heuristic": self.analyzed_heuristic,
            "recommended": self.recommended, "errors": self.errors,
            "sources": self.source_results, "filter_reasons": self.filter_reasons,
        }


# --------------------------------------------------------------------------- #
# FETCH
# --------------------------------------------------------------------------- #
async def _fetch_all(
    plan: list[tuple[str, SourceTarget]],
    on_progress: Callable[[int, int], None] | None = None,
) -> list[FetchResult]:
    """Consulta todas las fuentes en paralelo.

    `on_progress(objetivos_listos, avisos_leidos)` se llama a medida que cada
    fuente termina, para que la pantalla pueda mostrar el avance en vivo: una
    corrida completa tarda varios minutos y sin esto el botón parece colgado.
    """
    semaphore = asyncio.Semaphore(settings.http_max_concurrency)
    results: list[FetchResult] = []

    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers={"User-Agent": settings.http_user_agent, "Accept": "application/json"},
        follow_redirects=True,
    ) as client:

        async def run_one(source_key: str, target: SourceTarget) -> FetchResult:
            async with semaphore:
                source = get_source(source_key)
                source._client = client       # cliente compartido
                source._owns_client = False
                return await source.run(target)

        tasks = [run_one(key, target) for key, target in plan]
        leidos = 0
        for coro in asyncio.as_completed(tasks):
            try:
                resultado = await coro
                results.append(resultado)
                leidos += len(resultado.jobs)
            except Exception as exc:  # noqa: BLE001 - nunca debería llegar acá
                logger.exception("fallo no capturado en una fuente: %s", exc)
            if on_progress is not None:
                on_progress(len(results), leidos)
    return results


# --------------------------------------------------------------------------- #
# PERSISTENCIA + DEDUPE
# --------------------------------------------------------------------------- #
def _ingest(db: Session, results: list[FetchResult], summary: RunSummary, run: SearchRun) -> list[Job]:
    """Normaliza, deduplica y persiste. Devuelve los jobs nuevos o actualizados."""
    touched: list[Job] = []
    # Un mismo aviso puede llegar dos veces en la misma corrida (p. ej. dos
    # categorías del mismo agregador): se resuelve en memoria, no contra la DB.
    seen_in_run: set[tuple[str, str]] = set()

    for result in results:
        summary.sources_queried += 1
        created = duplicates = 0

        if result.status == "error":
            summary.sources_failed += 1
            summary.errors.append({"source": result.source, "target": result.target,
                                   "error": result.error})

        for raw in result.jobs:
            summary.raw_jobs += 1
            try:
                norm = normalize(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("normalización falló (%s): %s", raw.source, exc)
                continue
            if not norm.job_title or not norm.url:
                summary.filtered_out += 1
                continue

            # Gate barato: geografía y nivel evidente, antes de tocar la base (§38)
            decision_pre = should_ingest(
                title=norm.job_title, location=norm.location,
                description=norm.description, remote_type=norm.remote_type,
            )
            if not decision_pre.keep:
                summary.filtered_out += 1
                summary.filter_reasons[decision_pre.reason.split("(")[0].strip()] = (
                    summary.filter_reasons.get(decision_pre.reason.split("(")[0].strip(), 0) + 1
                )
                continue

            # 1) ¿Ya lo vimos por esta misma fuente?
            occurrence_key = (norm.source, norm.source_job_id)
            if occurrence_key in seen_in_run:
                summary.duplicates += 1
                duplicates += 1
                continue
            seen_in_run.add(occurrence_key)
            occurrence = db.scalars(
                select(JobSourceOccurrence).where(
                    JobSourceOccurrence.source == norm.source,
                    JobSourceOccurrence.source_job_id == norm.source_job_id,
                )
            ).first()
            if occurrence is not None:
                occurrence.last_seen_at = utcnow()
                job = db.get(Job, occurrence.job_id)
                if job:
                    job.last_seen_date = utcnow()
                    job.is_active = True
                    if norm.description and len(norm.description) > len(job.description or ""):
                        job.description = norm.description
                        touched.append(job)
                summary.updated_jobs += 1
                continue

            # 2) ¿Es el mismo puesto visto en otra fuente?
            decision = find_duplicate(
                db, company=norm.company, title=norm.job_title, location=norm.location,
                description_hash=norm.description_hash, fingerprint=norm.fingerprint,
            )
            if decision.action == "duplicate" and decision.existing is not None:
                existing = decision.existing
                if is_repost(existing, norm.publication_date):
                    existing.is_repost = True
                    summary.reposts += 1
                merge_into(existing, source=norm.source, url=norm.url,
                           apply_url=norm.apply_url, description=norm.description,
                           publication_date=norm.publication_date)
                db.add(JobSourceOccurrence(job_id=existing.id, source=norm.source,
                                           source_job_id=norm.source_job_id, url=norm.url))
                db.flush()
                duplicates += 1
                summary.duplicates += 1
                continue

            # 3) Nuevo
            company = get_or_create_company(db, norm.company)
            job = Job(
                job_id=norm.job_id, source=norm.source, source_job_id=norm.source_job_id,
                url=norm.url, apply_url=norm.apply_url, job_title=norm.job_title,
                title_normalized=norm.title_normalized, company=norm.company,
                company_normalized=norm.company_normalized, company_id=company.id,
                location=norm.location, location_city=norm.location_city,
                location_country=norm.location_country, remote_type=norm.remote_type,
                employment_type=norm.employment_type, description=norm.description,
                description_hash=norm.description_hash,
                publication_date=norm.publication_date,
                application_deadline=norm.application_deadline,
                salary_min=norm.salary_min, salary_max=norm.salary_max,
                salary_currency=norm.salary_currency,
                salary_is_published=norm.salary_is_published,
                fingerprint=norm.fingerprint, raw_payload=norm.raw_payload,
            )
            db.add(job)
            db.flush()
            db.add(JobSourceOccurrence(job_id=job.id, source=norm.source,
                                       source_job_id=norm.source_job_id, url=norm.url))
            db.flush()
            created += 1
            summary.new_jobs += 1
            touched.append(job)

        db.add(SourceLog(
            run_id=run.id, source=result.source, target=result.target, status=result.status,
            http_status=result.http_status, jobs_found=len(result.jobs), jobs_created=created,
            duplicates=duplicates, duration_ms=result.duration_ms, error=result.error,
        ))
        summary.source_results.append({
            "source": result.source, "target": result.target, "status": result.status,
            "found": len(result.jobs), "created": created, "duplicates": duplicates,
            "duration_ms": result.duration_ms, "error": result.error,
        })

        row = db.scalars(select(JobSource).where(JobSource.key == result.source)).first()
        if row:
            row.last_status = result.status
            row.last_run_at = utcnow()
            row.last_error = result.error
            row.last_found = len(result.jobs)
            row.avg_duration_ms = (
                result.duration_ms if row.avg_duration_ms is None
                else round(0.7 * row.avg_duration_ms + 0.3 * result.duration_ms, 1)
            )
    db.commit()
    return touched


# --------------------------------------------------------------------------- #
# ANÁLISIS
# --------------------------------------------------------------------------- #
async def _analyze(db: Session, jobs: list[Job], summary: RunSummary) -> None:
    profile = get_profile(db)
    candidate = build_context(profile, get_preference(db, "experience").get("policy"))
    weights = all_weights(db)
    personalization = adjustments(db)
    provider = build_provider()
    llm_budget = settings.ai_max_jobs_per_run
    user = get_user(db)

    try:
        for job in jobs:
            company = job.company_rel or (db.get(Job, job.id).company_rel if job.id else None)
            if company is None:
                company = get_or_create_company(db, job.company)
                job.company_id = company.id
            quality = load_company_quality(db, company)

            bundle = analyze_deterministic(
                title=job.job_title, description=job.description, company_name=job.company,
                location=job.location, remote_hint=job.remote_type,
                publication_date=job.publication_date, first_seen=job.first_seen_date,
                candidate=candidate,
                seniority_hint=(job.raw_payload or {}).get("seniority_hint"),
                company_quality=quality.score,
                company_confidence=quality.confidence, is_target_company=quality.is_target,
                salary_published=job.salary_is_published, weights=weights,
            )

            existing = db.scalars(
                select(JobAnalysis).where(JobAnalysis.job_id == job.id)
            ).first()
            # Caché (§38): mismo contenido -> no se reanaliza
            if existing and existing.analysis_input_hash == bundle.input_hash:
                continue

            if llm_budget > 0 and should_use_llm(bundle, provider):
                bundle = await refine_with_llm(bundle, provider, profile=profile, job=job)
                llm_budget -= 1
                summary.analyzed_llm += 1
            else:
                summary.analyzed_heuristic += 1

            # Personalización explícita por feedback (§46)
            family = getattr(bundle.role, "family", None)
            if family and family in personalization:
                delta = personalization[family]
                bundle.scores.final_score = round(
                    max(0.0, min(100.0, bundle.scores.final_score + delta)), 1
                )
                label = "sube" if delta > 0 else "baja"
                bundle.scores.match_reasons.append(
                    f"Ajuste por tus preferencias: {label} {abs(delta):g} puntos en esta área"
                )

            _persist_analysis(db, job, bundle, existing)
            if bundle.scores.recommendation in (
                Recommendation.APPLY_NOW.value, Recommendation.STRONG.value,
                Recommendation.WORTH_IT.value,
            ):
                summary.recommended += 1

            # Estado inicial para la usuaria
            state = db.scalars(
                select(JobState).where(JobState.user_id == user.id, JobState.job_id == job.id)
            ).first()
            if state is None:
                db.add(JobState(user_id=user.id, job_id=job.id, status=JobStatus.NEW.value))
        db.commit()
    finally:
        await provider.close()


def _persist_analysis(db: Session, job: Job, bundle, existing: JobAnalysis | None) -> None:
    scores = bundle.scores
    job.seniority = bundle.seniority.level.value
    job.experience_min = bundle.experience.min_years
    job.experience_max = bundle.experience.max_years
    job.experience_is_hard_requirement = bundle.experience.is_hard
    job.languages = bundle.languages.languages
    job.skills = bundle.skills.skills
    job.requirements = bundle.skills.requirements
    job.preferred_requirements = bundle.skills.preferred_requirements
    job.education_requirements = [
        r for r in bundle.skills.requirements
        if any(k in r.lower() for k in ("licenciat", "carrera", "degree", "estudi", "universi"))
    ][:5]

    row = existing or JobAnalysis(job_id=job.id)
    row.fit_score = scores.fit_score
    row.company_quality_score = scores.company_quality_score
    row.career_value_score = scores.career_value_score
    row.german_advantage_score = scores.german_advantage_score
    row.location_score = scores.location_score
    row.recency_score = scores.recency_score
    row.final_score = scores.final_score
    row.fit_breakdown = scores.fit_breakdown
    row.boosts = scores.boosts
    row.penalties = scores.penalties
    row.eligible = scores.eligible
    row.not_eligible_reason = scores.not_eligible_reason
    row.recommendation = scores.recommendation
    row.match_reasons = scores.match_reasons
    row.gaps = scores.gaps
    row.hard_blockers = scores.hard_blockers
    row.summary = scores.summary
    row.why_apply = scores.why_apply
    row.confidence = scores.confidence
    row.analyzer = bundle.analyzer
    row.analysis_input_hash = bundle.input_hash
    row.analyzed_at = utcnow()
    if existing is None:
        db.add(row)


def _refresh_company_scores(db: Session, jobs: list[Job]) -> None:
    seen: set[int] = set()
    for job in jobs:
        if job.company_id and job.company_id not in seen:
            seen.add(job.company_id)
            company = db.get(Company, job.company_id)
            if company:
                compute_company_quality(db, company)
    db.commit()


# --------------------------------------------------------------------------- #
# ENTRYPOINT
# --------------------------------------------------------------------------- #
async def reanalyze_all(only_missing: bool = False) -> dict:
    """Recalcula el análisis de los avisos guardados.

    Necesario cuando cambian los pesos de scoring o el perfil: el ranking se
    recalcula sin volver a consultar las fuentes.
    """
    summary = RunSummary(run_id=0)
    with session_scope() as db:
        stmt = select(Job).where(Job.is_duplicate.is_(False))
        jobs = list(db.scalars(stmt))
        if only_missing:
            analyzed = {a.job_id for a in db.scalars(select(JobAnalysis))}
            jobs = [j for j in jobs if j.id not in analyzed]
        # Forzar el recálculo invalidando el hash cacheado
        for analysis in db.scalars(select(JobAnalysis)):
            analysis.analysis_input_hash = None
        db.flush()
        for company in db.scalars(select(Company)):
            compute_company_quality(db, company)
        await _analyze(db, jobs, summary)
    return {"analizados": len(jobs), "recomendados": summary.recommended,
            "con_llm": summary.analyzed_llm, "con_reglas": summary.analyzed_heuristic}


async def run_pipeline(trigger: str = "manual", only_sources: list[str] | None = None,
                       notify: bool = True) -> dict:
    # Dos corridas a la vez sobre SQLite terminan en "database is locked".
    # Puede pasar fácil: el botón de la app mientras corre el agente diario.
    tomar_lock()
    try:
        return await _run_pipeline(trigger, only_sources, notify)
    finally:
        soltar_lock()


async def _run_pipeline(trigger: str, only_sources: list[str] | None,
                        notify: bool) -> dict:
    started = time.perf_counter()

    with session_scope() as db:
        sync_source_catalog(db)
        plan = build_plan(db, only_sources)
        run = SearchRun(trigger=trigger, status="running")
        db.add(run)
        db.flush()
        run_id = run.id
        db.commit()

    summary = RunSummary(run_id=run_id)
    logger.info("run=%s objetivos=%s", run_id, len(plan))

    def anotar_avance(objetivos: int, avisos: int) -> None:
        """Deja el avance en la fila del run, en su propia sesión y sin romper
        la corrida si la escritura falla."""
        try:
            with session_scope() as db_avance:
                fila = db_avance.get(SearchRun, run_id)
                if fila is not None:
                    fila.sources_queried = objetivos
                    fila.raw_jobs = avisos
        except Exception:  # noqa: BLE001 - el avance es cosmético
            logger.debug("no se pudo anotar el avance de la corrida %s", run_id)

    results = await _fetch_all(plan, anotar_avance) if plan else []

    with session_scope() as db:
        run = db.get(SearchRun, run_id)
        touched = _ingest(db, results, summary, run)
        job_ids = [j.id for j in touched]

    with session_scope() as db:
        jobs = db.scalars(select(Job).where(Job.id.in_(job_ids))).all() if job_ids else []
        _refresh_company_scores(db, jobs)
        await _analyze(db, jobs, summary)

    summary.duration_ms = int((time.perf_counter() - started) * 1000)
    summary.status = "ok" if summary.sources_failed < max(1, summary.sources_queried) else "degraded"

    with session_scope() as db:
        run = db.get(SearchRun, run_id)
        run.status = summary.status
        run.finished_at = utcnow()
        run.duration_ms = summary.duration_ms
        run.sources_queried = summary.sources_queried
        run.sources_failed = summary.sources_failed
        run.raw_jobs = summary.raw_jobs
        run.new_jobs = summary.new_jobs
        run.updated_jobs = summary.updated_jobs
        run.duplicates = summary.duplicates
        run.filtered_out = summary.filtered_out
        run.analyzed_llm = summary.analyzed_llm
        run.analyzed_heuristic = summary.analyzed_heuristic
        run.recommended = summary.recommended
        run.errors = summary.errors
        run.stats = {"reposts": summary.reposts, "sources": summary.source_results,
                     "filter_reasons": summary.filter_reasons}

        if notify and summary.new_jobs:
            digest = build_daily_digest(db, run_id)
            if digest:
                dispatch(db, digest, run_id)

    logger.info("run=%s ok nuevos=%s duplicados=%s recomendados=%s %sms",
                run_id, summary.new_jobs, summary.duplicates, summary.recommended,
                summary.duration_ms)
    return summary.to_dict()
