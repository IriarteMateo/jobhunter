"""company_quality_score con confianza explícita (§15, §50).

Regla dura: no se inventan datos. El score se arma con señales verificables:
  * tier curado en la lista semilla (dato editorial, se declara como tal)
  * tamaño declarado
  * si es empresa objetivo de la usuaria
  * señales observables en sus propios avisos (programa de graduados, ATS
    profesional, salario publicado, volumen de búsquedas)
Si no hay señales suficientes -> confidence = LOW y se muestra así en la UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.target_companies import SIZE_SIGNAL, TIER_BASE_SCORE, TIER_CONFIDENCE
from app.models import Company, CompanyScore, Confidence, Job, TargetCompany
from app.pipeline.text import normalize_company

NEUTRAL_SCORE = 50.0


@dataclass
class CompanyQuality:
    score: float = NEUTRAL_SCORE
    confidence: str = Confidence.LOW.value
    signals: dict = field(default_factory=dict)
    rationale: str = ""
    is_target: bool = False
    category: str | None = None
    german_relevant: bool = False


def get_or_create_company(db: Session, name: str) -> Company:
    normalized = normalize_company(name)
    company = db.scalars(
        select(Company).where(Company.normalized_name == normalized)
    ).first()
    if company is None:
        company = Company(name=name.strip() or normalized, normalized_name=normalized)
        db.add(company)
        db.flush()
    return company


def compute_company_quality(db: Session, company: Company) -> CompanyQuality:
    """Calcula (y persiste) la calidad de la empresa a partir de señales reales."""
    target = db.scalars(
        select(TargetCompany).where(TargetCompany.company_id == company.id)
    ).first()

    signals: dict = {}
    reasons: list[str] = []
    score = NEUTRAL_SCORE
    confidence = Confidence.LOW.value

    tier = (company.notes or "").strip() or None  # notes guarda el tier curado
    if tier in TIER_BASE_SCORE:
        score = TIER_BASE_SCORE[tier]
        confidence = TIER_CONFIDENCE[tier]
        signals["tier"] = tier
        reasons.append(f"empresa reconocida (tier {tier}) en la lista curada")

    if company.size_bucket in SIZE_SIGNAL:
        bonus = SIZE_SIGNAL[company.size_bucket]
        score += bonus
        signals["size_bucket"] = company.size_bucket
        if bonus:
            reasons.append(f"tamaño declarado: {company.size_bucket}")

    if target and target.enabled and not target.suggested:
        signals["target_company"] = True
        signals["priority"] = target.priority
        score += {1: 6.0, 2: 3.0, 3: 1.0}.get(target.priority, 0.0)
        reasons.append("está en tu lista de empresas objetivo")
        if tier not in TIER_BASE_SCORE and confidence == Confidence.LOW.value:
            confidence = Confidence.MEDIUM.value

    # --- Señales observables en sus propios avisos ---
    job_count = db.scalar(
        select(func.count(Job.id)).where(Job.company_id == company.id, Job.is_active.is_(True))
    ) or 0
    signals["active_jobs"] = job_count
    if job_count >= 8:
        score += 4.0
        reasons.append(f"{job_count} búsquedas activas detectadas")
    elif job_count >= 3:
        score += 2.0

    ats_sources = db.scalars(
        select(Job.source).where(Job.company_id == company.id).distinct()
    ).all()
    professional_ats = {"greenhouse", "lever", "ashby", "workday", "smartrecruiters",
                        "workable", "successfactors", "recruitee"}
    if set(ats_sources) & professional_ats:
        score += 3.0
        signals["professional_ats"] = sorted(set(ats_sources) & professional_ats)
        reasons.append("usa un ATS corporativo (proceso de selección estructurado)")
        if confidence == Confidence.LOW.value:
            confidence = Confidence.MEDIUM.value

    has_grad_program = db.scalar(
        select(func.count(Job.id)).where(
            Job.company_id == company.id,
            Job.seniority.in_(["Graduate", "Trainee", "Internship"]),
        )
    ) or 0
    if has_grad_program:
        score += 4.0
        signals["graduate_openings"] = has_grad_program
        reasons.append("publica posiciones de graduados / trainee / pasantía")

    published_salary = db.scalar(
        select(func.count(Job.id)).where(
            Job.company_id == company.id, Job.salary_is_published.is_(True)
        )
    ) or 0
    if published_salary:
        score += 2.0
        signals["publishes_salary"] = True
        reasons.append("publica rango salarial")

    score = round(max(0.0, min(100.0, score)), 1)
    if not reasons:
        reasons.append("información insuficiente: puntaje neutro")

    quality = CompanyQuality(
        score=score,
        confidence=confidence,
        signals=signals,
        rationale="; ".join(reasons),
        is_target=bool(target and target.enabled and not target.suggested),
        category=target.category if target else None,
        german_relevant=bool(target and target.german_relevant),
    )

    row = db.scalars(select(CompanyScore).where(CompanyScore.company_id == company.id)).first()
    if row is None:
        row = CompanyScore(company_id=company.id)
        db.add(row)
    row.quality_score = quality.score
    row.confidence = quality.confidence
    row.signals = quality.signals
    row.rationale = quality.rationale
    return quality


def load_company_quality(db: Session, company: Company) -> CompanyQuality:
    """Lee el score cacheado; lo calcula si no existe."""
    row = db.scalars(select(CompanyScore).where(CompanyScore.company_id == company.id)).first()
    if row is None:
        return compute_company_quality(db, company)
    target = db.scalars(
        select(TargetCompany).where(TargetCompany.company_id == company.id)
    ).first()
    return CompanyQuality(
        score=row.quality_score,
        confidence=row.confidence,
        signals=row.signals or {},
        rationale=row.rationale or "",
        is_target=bool(target and target.enabled and not target.suggested),
        category=target.category if target else None,
        german_relevant=bool(target and target.german_relevant),
    )
