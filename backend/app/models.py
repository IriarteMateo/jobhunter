"""Modelo de datos.

Compatible con SQLite (dev) y PostgreSQL (prod): se usa JSON portable y
timestamps naive en UTC.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Enums (se guardan como texto para evitar migraciones de tipos en Postgres)
# --------------------------------------------------------------------------- #
class Seniority(str, enum.Enum):
    INTERNSHIP = "Internship"
    TRAINEE = "Trainee"
    GRADUATE = "Graduate"
    ENTRY_LEVEL = "Entry Level"
    JUNIOR = "Junior"
    JUNIOR_PLUS = "Junior+"
    SEMI_SENIOR = "Semi Senior"
    SENIOR = "Senior"
    MANAGER = "Manager"
    DIRECTOR = "Director"
    UNKNOWN = "Unknown"


JUNIOR_FRIENDLY = {
    Seniority.INTERNSHIP,
    Seniority.TRAINEE,
    Seniority.GRADUATE,
    Seniority.ENTRY_LEVEL,
    Seniority.JUNIOR,
    Seniority.JUNIOR_PLUS,
}


class RemoteType(str, enum.Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class JobStatus(str, enum.Enum):
    NEW = "NEW"
    SEEN = "SEEN"
    SAVED = "SAVED"
    APPLIED = "APPLIED"
    INTERVIEW = "INTERVIEW"
    REJECTED = "REJECTED"
    DISCARDED = "DISCARDED"
    CLOSED = "CLOSED"


class Recommendation(str, enum.Enum):
    APPLY_NOW = "APPLY_NOW"
    STRONG = "STRONG"
    WORTH_IT = "WORTH_IT"
    OPTIONAL = "OPTIONAL"
    SKIP = "SKIP"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class Confidence(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# --------------------------------------------------------------------------- #
# Usuario y perfil
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    profile: Mapped["CandidateProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class CandidateProfile(Base):
    """Perfil editable de la candidata. Todo lo que alimenta el matching."""

    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    full_name: Mapped[str] = mapped_column(String(255), default="")
    headline: Mapped[str] = mapped_column(String(500), default="")

    # Formación
    university: Mapped[str] = mapped_column(String(255), default="")
    degree: Mapped[str] = mapped_column(String(255), default="")
    degree_field: Mapped[str] = mapped_column(String(255), default="")
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    education_extra: Mapped[list] = mapped_column(JSON, default=list)

    # Idiomas: [{"code":"de","name":"Alemán","level":"C1"}]
    languages: Mapped[list] = mapped_column(JSON, default=list)

    # Experiencia
    years_experience: Mapped[float] = mapped_column(Float, default=0.0)
    has_formal_experience: Mapped[bool] = mapped_column(Boolean, default=False)
    experience_items: Mapped[list] = mapped_column(JSON, default=list)

    # Skills y áreas
    skills: Mapped[list] = mapped_column(JSON, default=list)
    target_roles: Mapped[list] = mapped_column(JSON, default=list)
    role_families: Mapped[list] = mapped_column(JSON, default=list)
    excluded_areas: Mapped[list] = mapped_column(JSON, default=list)

    # Ubicación y modalidad
    city: Mapped[str] = mapped_column(String(120), default="")
    region: Mapped[str] = mapped_column(String(120), default="")
    country: Mapped[str] = mapped_column(String(120), default="Argentina")
    accepts_remote: Mapped[bool] = mapped_column(Boolean, default=True)
    accepts_hybrid: Mapped[bool] = mapped_column(Boolean, default=True)
    accepts_onsite: Mapped[bool] = mapped_column(Boolean, default=True)
    max_commute_km: Mapped[int | None] = mapped_column(Integer, default=45)
    preferred_locations: Mapped[list] = mapped_column(JSON, default=list)

    # Compensación
    salary_expectation_min: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str] = mapped_column(String(8), default="ARS")

    # Empresas
    favorite_companies: Mapped[list] = mapped_column(JSON, default=list)
    blocked_companies: Mapped[list] = mapped_column(JSON, default=list)

    # CV
    cv_filename: Mapped[str | None] = mapped_column(String(255))
    cv_text: Mapped[str | None] = mapped_column(Text)
    cv_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")


class CandidatePreference(Base):
    """Config clave/valor: pesos de scoring, thresholds, fuentes activas."""

    __tablename__ = "candidate_preferences"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_pref_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------- #
# Empresas
# --------------------------------------------------------------------------- #
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(500))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(255))
    size_bucket: Mapped[str | None] = mapped_column(String(64))
    hq_country: Mapped[str | None] = mapped_column(String(120))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    target: Mapped["TargetCompany"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
    score: Mapped["CompanyScore"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="company_rel", foreign_keys="Job.company_id"
    )


class TargetCompany(Base):
    """Empresa objetivo + configuración de su career page / ATS."""

    __tablename__ = "target_companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), unique=True)
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1 alta, 2 media, 3 baja
    category: Mapped[str | None] = mapped_column(String(120))
    german_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    ats_type: Mapped[str | None] = mapped_column(String(64))   # greenhouse|lever|ashby|smartrecruiters|workable
    ats_token: Mapped[str | None] = mapped_column(String(255))
    careers_url: Mapped[str | None] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    suggested: Mapped[bool] = mapped_column(Boolean, default=False)  # sugerida, no confirmada
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    company: Mapped[Company] = relationship(back_populates="target")


class CompanyScore(Base):
    __tablename__ = "company_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), unique=True)
    quality_score: Mapped[float] = mapped_column(Float, default=50.0)
    confidence: Mapped[str] = mapped_column(String(16), default=Confidence.LOW.value)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship(back_populates="score")


# --------------------------------------------------------------------------- #
# Fuentes
# --------------------------------------------------------------------------- #
class JobSource(Base):
    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(32))  # ats | board | aggregator | careers
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_config: Mapped[bool] = mapped_column(Boolean, default=False)
    compliance_note: Mapped[str | None] = mapped_column(Text)
    last_status: Mapped[str | None] = mapped_column(String(32))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_found: Mapped[int] = mapped_column(Integer, default=0)
    avg_duration_ms: Mapped[float | None] = mapped_column(Float)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


# --------------------------------------------------------------------------- #
# Empleos
# --------------------------------------------------------------------------- #
class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_fingerprint", "fingerprint"),
        Index("ix_jobs_first_seen", "first_seen_date"),
        Index("ix_jobs_company_title", "company_normalized", "title_normalized"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Origen canónico
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_job_id: Mapped[str] = mapped_column(String(255))
    original_source: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(1000))
    apply_url: Mapped[str | None] = mapped_column(String(1000))

    # Identidad
    job_title: Mapped[str] = mapped_column(String(500))
    title_normalized: Mapped[str] = mapped_column(String(500), default="")
    company: Mapped[str] = mapped_column(String(255))
    company_normalized: Mapped[str] = mapped_column(String(255), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))

    # Ubicación / modalidad
    location: Mapped[str | None] = mapped_column(String(500))
    location_city: Mapped[str | None] = mapped_column(String(255))
    location_country: Mapped[str | None] = mapped_column(String(120))
    remote_type: Mapped[str] = mapped_column(String(16), default=RemoteType.UNKNOWN.value)
    employment_type: Mapped[str | None] = mapped_column(String(64))

    # Contenido
    description: Mapped[str | None] = mapped_column(Text)
    description_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    preferred_requirements: Mapped[list] = mapped_column(JSON, default=list)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    education_requirements: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)

    # Seniority / experiencia
    seniority: Mapped[str] = mapped_column(String(32), default=Seniority.UNKNOWN.value)
    experience_min: Mapped[float | None] = mapped_column(Float)
    experience_max: Mapped[float | None] = mapped_column(Float)
    experience_is_hard_requirement: Mapped[bool] = mapped_column(Boolean, default=False)

    # Salario (sólo si viene publicado)
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    # Fechas
    publication_date: Mapped[datetime | None] = mapped_column(DateTime)
    first_seen_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime)

    # Estado del registro
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    is_repost: Mapped[bool] = mapped_column(Boolean, default=False)
    reposted_from_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    fingerprint: Mapped[str] = mapped_column(String(64), default="")

    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    company_rel: Mapped[Company | None] = relationship(
        back_populates="jobs", foreign_keys=[company_id]
    )
    analysis: Mapped["JobAnalysis"] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    occurrences: Mapped[list["JobSourceOccurrence"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    state: Mapped["JobState"] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class JobSourceOccurrence(Base):
    """Cada vez que un empleo aparece en una fuente (para dedup multi-fuente)."""

    __tablename__ = "job_source_occurrences"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_occurrence_source_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64))
    source_job_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1000))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    job: Mapped[Job] = relationship(back_populates="occurrences")


class JobAnalysis(Base):
    """Resultado del motor de matching (determinístico + LLM)."""

    __tablename__ = "job_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)

    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    company_quality_score: Mapped[float] = mapped_column(Float, default=50.0)
    career_value_score: Mapped[float] = mapped_column(Float, default=0.0)
    german_advantage_score: Mapped[float] = mapped_column(Float, default=0.0)
    location_score: Mapped[float] = mapped_column(Float, default=0.0)
    recency_score: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    fit_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    boosts: Mapped[list] = mapped_column(JSON, default=list)
    penalties: Mapped[list] = mapped_column(JSON, default=list)

    eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    not_eligible_reason: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(String(32), default=Recommendation.OPTIONAL.value)

    match_reasons: Mapped[list] = mapped_column(JSON, default=list)
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    hard_blockers: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    why_apply: Mapped[str | None] = mapped_column(Text)

    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    analyzer: Mapped[str] = mapped_column(String(32), default="heuristic")
    analysis_input_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    job: Mapped[Job] = relationship(back_populates="analysis")


class JobState(Base):
    """Estado del empleo para la usuaria (consolida saved/dismissed/applied)."""

    __tablename__ = "job_states"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_state_user_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))

    status: Mapped[str] = mapped_column(String(24), default=JobStatus.NEW.value, index=True)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime)
    dismiss_reason: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="state")
    application: Mapped["Application"] = relationship(
        back_populates="state", uselist=False, cascade="all, delete-orphan"
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("job_states.id", ondelete="CASCADE"), unique=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    stage: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    recruiter_contact: Mapped[str | None] = mapped_column(String(255))
    next_interview_at: Mapped[datetime | None] = mapped_column(DateTime)
    expected_salary: Mapped[float | None] = mapped_column(Float)
    outcome: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    state: Mapped[JobState] = relationship(back_populates="application")


class FeedbackEvent(Base):
    """Señal explícita de la usuaria, base para personalización futura."""

    __tablename__ = "feedback_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(32))  # interested|not_interested|applied|dismissed
    reason: Mapped[str | None] = mapped_column(String(255))
    features: Mapped[dict] = mapped_column(JSON, default=dict)  # snapshot para aprender
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# --------------------------------------------------------------------------- #
# Ejecución y observabilidad
# --------------------------------------------------------------------------- #
class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(24), default="manual")  # manual|scheduled
    status: Mapped[str] = mapped_column(String(24), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    sources_queried: Mapped[int] = mapped_column(Integer, default=0)
    sources_failed: Mapped[int] = mapped_column(Integer, default=0)
    raw_jobs: Mapped[int] = mapped_column(Integer, default=0)
    new_jobs: Mapped[int] = mapped_column(Integer, default=0)
    updated_jobs: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    filtered_out: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_llm: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_heuristic: Mapped[int] = mapped_column(Integer, default=0)
    recommended: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)

    logs: Mapped[list["SourceLog"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class SourceLog(Base):
    __tablename__ = "source_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24))  # ok|error|skipped
    http_status: Mapped[int | None] = mapped_column(Integer)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_created: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[SearchRun] = relationship(back_populates="logs")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("search_runs.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(24))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
