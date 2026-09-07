"""Esquemas de entrada/salida de la API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------- Perfil --------------------------- #
class LanguageIn(BaseModel):
    code: str
    name: str
    level: str = ""


class ProfileOut(ORMModel):
    id: int
    full_name: str
    headline: str
    university: str
    degree: str
    degree_field: str
    graduation_year: int | None
    education_extra: list = []
    languages: list = []
    years_experience: float
    has_formal_experience: bool
    experience_items: list = []
    skills: list = []
    target_roles: list = []
    role_families: list = []
    excluded_areas: list = []
    city: str
    region: str
    country: str
    accepts_remote: bool
    accepts_hybrid: bool
    accepts_onsite: bool
    max_commute_km: int | None
    preferred_locations: list = []
    salary_expectation_min: float | None
    salary_currency: str
    favorite_companies: list = []
    blocked_companies: list = []
    cv_filename: str | None
    updated_at: datetime


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    university: str | None = None
    degree: str | None = None
    degree_field: str | None = None
    graduation_year: int | None = None
    education_extra: list | None = None
    languages: list | None = None
    years_experience: float | None = None
    has_formal_experience: bool | None = None
    experience_items: list | None = None
    skills: list | None = None
    target_roles: list | None = None
    role_families: list | None = None
    excluded_areas: list | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    accepts_remote: bool | None = None
    accepts_hybrid: bool | None = None
    accepts_onsite: bool | None = None
    max_commute_km: int | None = None
    preferred_locations: list | None = None
    salary_expectation_min: float | None = None
    salary_currency: str | None = None
    favorite_companies: list | None = None
    blocked_companies: list | None = None


# --------------------------- Empleos --------------------------- #
class AnalysisOut(ORMModel):
    fit_score: float
    company_quality_score: float
    career_value_score: float
    german_advantage_score: float
    location_score: float
    recency_score: float
    final_score: float
    fit_breakdown: dict = {}
    boosts: list = []
    penalties: list = []
    eligible: bool
    not_eligible_reason: str | None
    recommendation: str
    match_reasons: list = []
    gaps: list = []
    hard_blockers: list = []
    summary: str | None
    why_apply: str | None
    confidence: float
    analyzer: str
    analyzed_at: datetime


class JobCard(BaseModel):
    id: int
    job_id: str
    job_title: str
    company: str
    company_logo: str | None = None
    company_quality_confidence: str = "LOW"
    is_target_company: bool = False
    location: str | None
    remote_type: str
    employment_type: str | None
    seniority: str
    experience_label: str
    languages: list = []
    skills: list = []
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_is_published: bool = False
    source: str
    sources: list[str] = []
    url: str
    apply_url: str | None
    publication_date: datetime | None
    first_seen_date: datetime
    is_new_today: bool = False
    is_repost: bool = False
    status: str = "NEW"
    category_emoji: str = ""
    category_label: str = ""
    role_family: str | None = None
    analysis: AnalysisOut | None = None


class JobDetail(JobCard):
    description: str | None = None
    resumen: dict | None = None
    requirements: list = []
    preferred_requirements: list = []
    education_requirements: list = []
    application_deadline: datetime | None = None
    occurrences: list = []
    application: dict | None = None
    notes: str | None = None


class JobListOut(BaseModel):
    total: int
    items: list[JobCard]
    page: int
    page_size: int


class JobImportIn(BaseModel):
    url: str | None = None
    text: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None


class JobImportOut(BaseModel):
    job_id: int
    created: bool
    merged_with_existing: bool
    fetched_url: bool
    message: str
    job: "JobDetail | None" = None


class StatusUpdate(BaseModel):
    status: str
    reason: str | None = None
    notes: str | None = None
    recruiter_contact: str | None = None
    stage: str | None = None
    next_interview_at: datetime | None = None
    expected_salary: float | None = None


# --------------------------- Empresas --------------------------- #
class TargetCompanyIn(BaseModel):
    name: str
    category: str | None = None
    priority: int = 2
    german_relevant: bool = False
    ats_type: str | None = None
    ats_token: str | None = None
    careers_url: str | None = None
    enabled: bool = True


class AtsDetectIn(BaseModel):
    careers_url: str
    name: str = ""
    verify: bool = True


class CompanyOverview(BaseModel):
    company_id: int
    name: str
    category: str | None = None
    ats_type: str | None = None
    ats_label: str | None = None
    is_target: bool = False
    german_relevant: bool = False
    quality_score: float | None = None
    quality_confidence: str | None = None
    total_jobs: int = 0
    eligible_jobs: int = 0
    recommended_jobs: int = 0
    new_today: int = 0
    best_score: float | None = None
    logo_url: str | None = None


class TargetCompanyOut(BaseModel):
    id: int
    company_id: int
    name: str
    category: str | None
    priority: int
    german_relevant: bool
    ats_type: str | None
    ats_token: str | None
    careers_url: str | None
    enabled: bool
    suggested: bool
    quality_score: float | None = None
    quality_confidence: str | None = None
    active_jobs: int = 0


# --------------------------- Fuentes / runs --------------------------- #
class SourceOut(ORMModel):
    key: str
    label: str
    kind: str
    enabled: bool
    requires_config: bool
    compliance_note: str | None
    last_status: str | None
    last_run_at: datetime | None
    last_error: str | None
    last_found: int
    avg_duration_ms: float | None


class SourceToggle(BaseModel):
    enabled: bool


class RunOut(ORMModel):
    id: int
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    sources_queried: int
    sources_failed: int
    raw_jobs: int
    new_jobs: int
    updated_jobs: int
    duplicates: int
    filtered_out: int
    analyzed_llm: int
    analyzed_heuristic: int
    recommended: int
    errors: list = []
    stats: dict = {}


class RunRequest(BaseModel):
    sources: list[str] | None = None
    notify: bool = True


# --------------------------- Config --------------------------- #
class PreferenceUpdate(BaseModel):
    value: dict = Field(default_factory=dict)
