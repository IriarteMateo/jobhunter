"""Perfil, empresas, fuentes, corridas, estadísticas y configuración."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import BASE_DIR, settings
from app.db import get_db
from app.models import (
    Company,
    CompanyScore,
    Job,
    JobAnalysis,
    JobSource,
    Notification,
    SearchRun,
    SourceLog,
    TargetCompany,
    utcnow,
)
from app.pipeline.runlock import RunInProgress, esta_corriendo
from app.pipeline.runner import reanalyze_all, run_pipeline
from app.schemas import (
    AtsDetectIn,
    CompanyOverview,
    PreferenceUpdate,
    ProfileOut,
    ProfileUpdate,
    RunOut,
    RunRequest,
    SourceOut,
    SourceToggle,
    TargetCompanyIn,
    TargetCompanyOut,
)
from app.services import cv as cv_service
from app.services import feedback as feedback_service
from app.services.companies import compute_company_quality, get_or_create_company
from app.services.notifications import build_daily_digest
from app.services.profile import PREF_KEYS, get_preference, get_profile, get_user, set_preference
from app.services.stats import today_summary, weekly_stats
from app.sources.registry import SOURCE_CLASSES, sync_source_catalog
from app.sources.restricted import SavedSearchLinksSource

router = APIRouter(prefix="/api", tags=["app"])


# --------------------------------- Perfil --------------------------------- #
@router.get("/profile", response_model=ProfileOut)
def read_profile(db: Session = Depends(get_db)):
    profile = get_profile(db)
    db.commit()
    return profile


@router.put("/profile", response_model=ProfileOut)
def update_profile(payload: ProfileUpdate, db: Session = Depends(get_db)):
    profile = get_profile(db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    profile.has_formal_experience = bool(profile.years_experience and profile.years_experience > 0) \
        if payload.years_experience is not None else profile.has_formal_experience
    db.commit()
    return profile


@router.post("/profile/cv")
async def upload_cv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Carga el CV y devuelve una PROPUESTA de perfil, sin sobrescribir nada."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(422, "sólo se aceptan archivos PDF")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "el archivo supera los 8 MB")
    try:
        text = cv_service.extract_text(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"no se pudo leer el PDF: {exc}") from exc

    profile = get_profile(db)
    profile.cv_filename = file.filename
    profile.cv_text = text[:100_000]
    profile.cv_uploaded_at = utcnow()
    db.commit()
    return {"filename": file.filename, "propuesta": cv_service.parse_cv(text)}


# -------------------------------- Empresas -------------------------------- #
@router.get("/companies", response_model=list[TargetCompanyOut])
def list_target_companies(db: Session = Depends(get_db), include_suggested: bool = True):
    rows = db.execute(
        select(TargetCompany, Company).join(Company, TargetCompany.company_id == Company.id)
        .order_by(TargetCompany.priority, Company.name)
    ).all()
    scores = {s.company_id: s for s in db.scalars(select(CompanyScore))}
    counts = dict(db.execute(
        select(Job.company_id, func.count(Job.id)).where(Job.is_active.is_(True))
        .group_by(Job.company_id)
    ).all())
    out = []
    for tc, company in rows:
        if tc.suggested and not include_suggested:
            continue
        score = scores.get(company.id)
        out.append(TargetCompanyOut(
            id=tc.id, company_id=company.id, name=company.name, category=tc.category,
            priority=tc.priority, german_relevant=tc.german_relevant, ats_type=tc.ats_type,
            ats_token=tc.ats_token, careers_url=tc.careers_url, enabled=tc.enabled,
            suggested=tc.suggested,
            quality_score=score.quality_score if score else None,
            quality_confidence=score.confidence if score else None,
            active_jobs=counts.get(company.id, 0),
        ))
    return out


@router.post("/companies", response_model=TargetCompanyOut)
def add_target_company(payload: TargetCompanyIn, db: Session = Depends(get_db)):
    company = get_or_create_company(db, payload.name)
    target = db.scalars(
        select(TargetCompany).where(TargetCompany.company_id == company.id)
    ).first()
    if target is None:
        target = TargetCompany(company_id=company.id)
        db.add(target)
    target.category = payload.category
    target.priority = payload.priority
    target.german_relevant = payload.german_relevant
    target.ats_type = payload.ats_type
    target.ats_token = payload.ats_token
    target.careers_url = payload.careers_url
    target.enabled = payload.enabled
    target.suggested = False
    db.flush()
    quality = compute_company_quality(db, company)
    db.commit()
    return TargetCompanyOut(
        id=target.id, company_id=company.id, name=company.name, category=target.category,
        priority=target.priority, german_relevant=target.german_relevant,
        ats_type=target.ats_type, ats_token=target.ats_token, careers_url=target.careers_url,
        enabled=target.enabled, suggested=False, quality_score=quality.score,
        quality_confidence=quality.confidence,
    )


@router.post("/companies/detect")
async def detect_company_ats(payload: AtsDetectIn):
    """Identifica sobre qué ATS corre la sección de empleos de una empresa.

    Lee una única página pública para reconocer la plataforma y, si hay conector,
    consulta su API para confirmar que funciona antes de proponer la configuración.
    """
    from app.services.ats_detector import detect

    result = await detect(payload.careers_url, payload.name, payload.verify)
    return result.as_dict()


@router.delete("/companies/{target_id}")
def remove_target_company(target_id: int, db: Session = Depends(get_db)):
    target = db.get(TargetCompany, target_id)
    if target is None:
        raise HTTPException(404, "empresa objetivo no encontrada")
    db.delete(target)
    db.commit()
    return {"ok": True}


@router.get("/companies/overview", response_model=list[CompanyOverview])
def companies_overview(db: Session = Depends(get_db), only_with_jobs: bool = False):
    """Todas las empresas del radar con el conteo real de sus oportunidades."""
    from datetime import timedelta

    from app.models import JobAnalysis, Recommendation, utcnow
    from app.sources.registry import SOURCE_CLASSES

    threshold = float(get_preference(db, "display").get("min_display_score", 70.0))
    desde = utcnow() - timedelta(hours=24)

    rows = db.execute(
        select(TargetCompany, Company).join(Company, TargetCompany.company_id == Company.id)
    ).all()
    scores = {s.company_id: s for s in db.scalars(select(CompanyScore))}

    agregados: dict[int, dict] = {}
    for company_id, total, elegibles, recomendados, nuevos, mejor in db.execute(
        select(
            Job.company_id,
            func.count(Job.id),
            func.sum(case((JobAnalysis.eligible.is_(True), 1), else_=0)),
            func.sum(case(((JobAnalysis.final_score >= threshold)
                           & JobAnalysis.eligible.is_(True), 1), else_=0)),
            func.sum(case((Job.first_seen_date >= desde, 1), else_=0)),
            func.max(JobAnalysis.final_score),
        )
        .join(JobAnalysis, JobAnalysis.job_id == Job.id)
        .where(Job.is_duplicate.is_(False))
        .group_by(Job.company_id)
    ).all():
        agregados[company_id] = {
            "total": total or 0, "elegibles": elegibles or 0,
            "recomendados": recomendados or 0, "nuevos": nuevos or 0,
            "mejor": round(float(mejor), 1) if mejor is not None else None,
        }

    salida: list[CompanyOverview] = []
    for target, company in rows:
        datos = agregados.get(company.id, {})
        if only_with_jobs and not datos.get("total"):
            continue
        score = scores.get(company.id)
        cls = SOURCE_CLASSES.get(target.ats_type or "")
        salida.append(CompanyOverview(
            company_id=company.id, name=company.name, category=target.category,
            ats_type=target.ats_type, ats_label=(cls.label if cls else None),
            is_target=bool(target.enabled and not target.suggested),
            german_relevant=target.german_relevant,
            quality_score=score.quality_score if score else None,
            quality_confidence=score.confidence if score else None,
            total_jobs=datos.get("total", 0), eligible_jobs=datos.get("elegibles", 0),
            recommended_jobs=datos.get("recomendados", 0), new_today=datos.get("nuevos", 0),
            best_score=datos.get("mejor"), logo_url=company.logo_url,
        ))
    salida.sort(key=lambda c: (-c.recommended_jobs, -c.total_jobs, c.name))
    return salida


@router.get("/companies/radar")
def companies_radar(db: Session = Depends(get_db)):
    """Qué está mirando la app en cada corrida, y qué no.

    Distingue lo que realmente se consulta (empresa con conector activo) de lo
    que sólo figura en la lista de objetivos sin forma de consultarla.
    """
    from collections import defaultdict

    from app.sources.registry import COMPANY_DRIVEN, build_plan

    plan = build_plan(db)
    company_targets = [(k, t) for k, t in plan if k in COMPANY_DRIVEN]
    aggregator_targets = [(k, t) for k, t in plan if k not in COMPANY_DRIVEN]

    last_run = db.scalars(select(SearchRun).order_by(SearchRun.id.desc())).first()
    logs: dict[tuple[str, str | None], SourceLog] = {}
    if last_run:
        for log in db.scalars(select(SourceLog).where(SourceLog.run_id == last_run.id)):
            logs[(log.source, log.target)] = log

    grouped: dict[str, list[dict]] = defaultdict(list)
    for source_key, target in company_targets:
        log = logs.get((source_key, target.label))
        grouped[source_key].append({
            "name": target.label,
            "jobs_found": log.jobs_found if log else None,
            "status": log.status if log else "sin ejecutar",
            "error": log.error if log else None,
        })

    active = [
        {"ats": ats, "label": SOURCE_CLASSES[ats].label if ats in SOURCE_CLASSES else ats,
         "count": len(items), "companies": sorted(items, key=lambda c: c["name"])}
        for ats, items in sorted(grouped.items(), key=lambda kv: -len(kv[1]))
    ]

    rows = db.execute(
        select(TargetCompany, Company).join(Company, TargetCompany.company_id == Company.id)
    ).all()
    without = sorted(
        ({"name": company.name, "category": tc.category,
          "careers_url": tc.careers_url if (tc.ats_type is None) else None}
         for tc, company in rows if not tc.ats_type),
        key=lambda c: c["name"],
    )

    return {
        "total_objetivos": len(plan),
        "empresas_consultadas": len(company_targets),
        "agregadores": sorted({t.label.split(" · ")[0] for _, t in aggregator_targets}),
        "agregador_objetivos": len(aggregator_targets),
        "por_ats": active,
        "sin_conector": without,
        "ultima_corrida": {
            "id": last_run.id, "finished_at": last_run.finished_at,
            "raw_jobs": last_run.raw_jobs, "new_jobs": last_run.new_jobs,
        } if last_run else None,
    }


@router.get("/companies/suggestions")
def company_suggestions(db: Session = Depends(get_db), min_jobs: int = 2, min_score: float = 70.0):
    """Empresas fuera de la lista que vienen publicando buenas oportunidades (§49).

    Sólo sugiere: nunca las agrega automáticamente.
    """
    target_ids = {t.company_id for t in db.scalars(select(TargetCompany))}
    rows = db.execute(
        select(Job.company_id, Company.name, func.count(Job.id), func.avg(JobAnalysis.final_score))
        .join(JobAnalysis, JobAnalysis.job_id == Job.id)
        .join(Company, Company.id == Job.company_id)
        .where(JobAnalysis.final_score >= min_score, JobAnalysis.eligible.is_(True))
        .group_by(Job.company_id, Company.name)
        .having(func.count(Job.id) >= min_jobs)
        .order_by(func.avg(JobAnalysis.final_score).desc())
        .limit(15)
    ).all()
    return [
        {"company_id": cid, "name": name, "matching_jobs": count,
         "avg_score": round(float(avg), 1),
         "texto": f"Agregar {name} a empresas objetivo: {count} oportunidades relevantes "
                  f"(promedio {round(float(avg), 1)}%)"}
        for cid, name, count, avg in rows if cid not in target_ids
    ]


# -------------------------------- Fuentes --------------------------------- #
@router.get("/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    sync_source_catalog(db)
    return list(db.scalars(select(JobSource).order_by(JobSource.kind, JobSource.key)))


@router.patch("/sources/{key}", response_model=SourceOut)
def toggle_source(key: str, payload: SourceToggle, db: Session = Depends(get_db)):
    row = db.scalars(select(JobSource).where(JobSource.key == key)).first()
    if row is None:
        raise HTTPException(404, "fuente no encontrada")
    row.enabled = payload.enabled
    db.commit()
    return row


@router.get("/sources/health")
def sources_health(db: Session = Depends(get_db)):
    sync_source_catalog(db)
    rows = list(db.scalars(select(JobSource)))
    return {
        "sources": [
            {
                "key": r.key, "label": r.label, "kind": r.kind, "enabled": r.enabled,
                "status": r.last_status or ("sin ejecutar" if r.enabled else "deshabilitada"),
                "last_run_at": r.last_run_at, "last_found": r.last_found,
                "last_error": r.last_error, "avg_duration_ms": r.avg_duration_ms,
                "compliance_note": r.compliance_note,
                "compliance_level": getattr(SOURCE_CLASSES.get(r.key), "compliance", "unknown"),
            }
            for r in rows
        ],
        "html_scraping_enabled": settings.enable_html_scraping,
        "database": settings.database_url,
        "project_dir": str(BASE_DIR.parent),
        "notificaciones": {
            "escritorio": settings.notify_desktop_enabled,
            "email": settings.notify_email_enabled,
            "telegram": settings.notify_telegram_enabled,
        },
    }


@router.get("/sources/search-links")
def search_links(db: Session = Depends(get_db)):
    """Links de búsqueda para portales que no permiten scraping (§8)."""
    profile = get_profile(db)
    queries = (profile.target_roles or [])[:8] or ["Business Analyst"]
    location = f"{profile.city}, {profile.country}" if profile.city else "Buenos Aires, Argentina"
    db.commit()
    return {"location": location, "links": SavedSearchLinksSource.build_links(queries, location)}


# --------------------------------- Runs ----------------------------------- #
@router.post("/runs")
async def trigger_run(payload: RunRequest | None = None, db: Session = Depends(get_db)):
    """Ejecución manual: BUSCAR NUEVOS EMPLEOS AHORA (§30).

    Arranca la corrida y devuelve al instante. Una corrida completa consulta 74
    objetivos y tarda varios minutos: esperarla dentro de la request HTTP la
    hacía caer por timeout del proxy, y el usuario veía un 500 aunque la
    búsqueda estuviera funcionando perfecto.

    El progreso se sigue con GET /api/runs/{id}.
    """
    payload = payload or RunRequest()
    if esta_corriendo():
        raise HTTPException(409, "Ya hay una búsqueda en curso.")

    async def en_segundo_plano() -> None:
        try:
            await run_pipeline("manual", payload.sources, payload.notify)
        except RunInProgress:
            pass
        except Exception:  # noqa: BLE001 - queda registrado en el SearchRun
            logging.getLogger(__name__).exception("la búsqueda manual falló")

    asyncio.create_task(en_segundo_plano())
    # Le damos un momento para que cree la fila de SearchRun y poder devolver su id
    for _ in range(20):
        await asyncio.sleep(0.25)
        ultima = db.scalars(select(SearchRun).order_by(SearchRun.id.desc())).first()
        if ultima is not None and ultima.status == "running":
            db.commit()
            return {"run_id": ultima.id, "status": "running",
                    "mensaje": "Búsqueda iniciada. Consulta unas 74 fuentes, tarda unos minutos."}
        db.expire_all()
    return {"run_id": None, "status": "running",
            "mensaje": "Búsqueda iniciada. Tarda unos minutos."}


@router.post("/runs/reanalyze")
async def trigger_reanalyze(only_missing: bool = False):
    """Recalcula scores con las reglas/pesos/perfil actuales, sin volver a scrapear."""
    return await reanalyze_all(only_missing)


@router.get("/runs", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db), limit: int = 20):
    return list(db.scalars(select(SearchRun).order_by(SearchRun.started_at.desc()).limit(limit)))


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(SearchRun, run_id)
    if run is None:
        raise HTTPException(404, "corrida no encontrada")
    return run


# ------------------------------ Dashboard --------------------------------- #
@router.get("/dashboard/today")
def dashboard_today(db: Session = Depends(get_db)):
    result = today_summary(db)
    db.commit()
    return result


@router.get("/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db)):
    result = weekly_stats(db)
    db.commit()
    return result


# ---------------------------- Notificaciones ------------------------------ #
@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db), limit: int = 20):
    user = get_user(db)
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc()).limit(limit)
    ).all()
    db.commit()
    return [
        {"id": n.id, "channel": n.channel, "subject": n.subject, "body": n.body,
         "status": n.status, "created_at": n.created_at, "error": n.error}
        for n in rows
    ]


@router.post("/notifications/test")
def test_notification(db: Session = Depends(get_db)):
    """Dispara una notificación de escritorio de prueba."""
    from app.services.notifications import _desktop_available, _send_desktop

    if not _desktop_available():
        raise HTTPException(422, "las notificaciones de escritorio requieren macOS")
    digest = build_daily_digest(db) or {
        "count": 0,
        "top": [{"emoji": "🔔", "score": 100,
                 "title": "Notificaciones activadas", "company": "Job Hunter"}],
    }
    try:
        _send_desktop(digest)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"no se pudo notificar: {exc}") from exc
    db.commit()
    return {"ok": True, "mensaje": "Mirá la esquina superior derecha de tu pantalla."}


@router.get("/notifications/preview")
def preview_digest(db: Session = Depends(get_db)):
    digest = build_daily_digest(db)
    db.commit()
    return digest or {"detail": "no hay novedades para notificar"}


# ------------------------------ Configuración ----------------------------- #
@router.get("/config")
def read_config(db: Session = Depends(get_db)):
    prefs = {key: get_preference(db, key) for key in PREF_KEYS}
    db.commit()
    return {
        "preferences": prefs,
        "ai_provider": settings.ai_provider,
        "ai_active": settings.ai_provider != "heuristic" and bool(
            settings.anthropic_api_key or settings.openai_api_key
        ),
        "timezone": settings.timezone,
        "daily_run": f"{settings.daily_run_hour:02d}:{settings.daily_run_minute:02d}",
        "scheduler_enabled": settings.scheduler_enabled,
        "html_scraping_enabled": settings.enable_html_scraping,
        "database": settings.database_url,
        "project_dir": str(BASE_DIR.parent),
        "notificaciones": {
            "escritorio": settings.notify_desktop_enabled,
            "email": settings.notify_email_enabled,
            "telegram": settings.notify_telegram_enabled,
        },
    }


@router.put("/config/{key}")
def update_config(key: str, payload: PreferenceUpdate, db: Session = Depends(get_db)):
    if key not in PREF_KEYS:
        raise HTTPException(404, f"clave de configuración desconocida: {key}")
    value = set_preference(db, key, payload.value)
    db.commit()
    return {key: value}


@router.get("/config/personalization")
def personalization(db: Session = Depends(get_db)):
    """Qué ajustes por feedback están activos (§46: nunca opaco)."""
    result = feedback_service.explain(db)
    db.commit()
    return {"ajustes": result,
            "nota": "Estos ajustes se calculan sólo con tus acciones de guardar, "
                    "aplicar y descartar. Podés desactivarlos en configuración."}
