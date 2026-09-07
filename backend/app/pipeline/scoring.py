"""Motor de scoring determinístico (§14-§19).

Produce fit_score, career_value_score, final_score, explicación y elegibilidad.
Es la primera capa: barata, auditable y suficiente para operar sin LLM. El LLM
(cuando está configurado) sólo refina sobre esta base.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from app.data.taxonomy import (
    EDUCATION_BUSINESS_TERMS,
    EDUCATION_HARD_BLOCKERS,
    GRADUATE_PROGRAM_TERMS,
    LOW_QUALITY_SIGNALS,
)
from app.models import JUNIOR_FRIENDLY, Recommendation, RemoteType, Seniority, utcnow
from app.pipeline.experience import ExperienceRequirement, experience_bucket
from app.pipeline.languages import LanguageAnalysis
from app.pipeline.location import LocationAnalysis
from app.pipeline.roles import RoleMatch
from app.pipeline.seniority import SeniorityResult
from app.pipeline.skills import SkillAnalysis, gap_severity
from app.pipeline.text import contains_any, found_terms, has_term, searchable

# --------------------------------------------------------------------------- #
# Pesos por defecto (§14). Editables desde configuración.
# --------------------------------------------------------------------------- #
DEFAULT_FIT_WEIGHTS = {
    "role": 20.0,
    "seniority": 25.0,
    "education": 15.0,
    "language": 15.0,
    "skills": 10.0,
    "location": 10.0,
    "other": 5.0,
}

DEFAULT_FINAL_WEIGHTS = {
    "fit": 0.60,
    "company": 0.20,
    "career": 0.15,
    "recency": 0.05,
}

DEFAULT_BOOSTS = {
    "no_experience_required": 6.0,
    "german_advantage": 6.0,
    "target_company": 5.0,
    "graduate_program": 5.0,
    "premium_internship": 3.0,
    "rare_opportunity": 3.0,
}

DEFAULT_PENALTIES = {
    "excess_experience": 12.0,
    "unknown_company": 5.0,
    "commission_only": 25.0,
    "informal_job": 15.0,
    "unrelated_role": 15.0,
    "suspicious_description": 12.0,
    "no_company": 10.0,
    "technical_heavy": 8.0,
}

# Compuerta de compatibilidad de rol
ROLE_GATE_FLOOR = 0.35     # multiplicador cuando el rol no tiene nada que ver
ROLE_GATE_FULL = 55.0      # a partir de acá el rol no penaliza
ROLE_ELIGIBILITY_MIN = 20.0  # por debajo, el aviso directamente no es para el perfil

# Política de experiencia: qué se descarta según el modo elegido (§12).
# Un perfil sin experiencia formal no debería ver puestos que piden recorrido.
EXPERIENCE_POLICY = {
    "strict": {
        "excluded_levels": {Seniority.SEMI_SENIOR, Seniority.SENIOR,
                            Seniority.MANAGER, Seniority.DIRECTOR},
        "max_hard_years": 1.0,     # un requisito duro desde 1 año ya descarta
        "max_soft_years": 1.0,     # y una preferencia de 1+ año, también
        "soft_penalty_per_year": 9.0,
        # Un aviso cuyo nivel no se puede confirmar no debería competir con los
        # que sí dicen ser de nivel inicial.
        "unknown_level_cap": 74.0,
    },
    "balanced": {
        "excluded_levels": {Seniority.SENIOR, Seniority.MANAGER, Seniority.DIRECTOR},
        "max_hard_years": 3.0,
        "max_soft_years": 5.0,
        "soft_penalty_per_year": 5.0,
        "unknown_level_cap": 79.0,
    },
    "open": {
        "excluded_levels": {Seniority.DIRECTOR},
        "max_hard_years": 99.0,
        "max_soft_years": 99.0,
        "soft_penalty_per_year": 2.0,
        "unknown_level_cap": 100.0,
    },
}

RECOMMENDATION_BANDS = [
    (90.0, Recommendation.APPLY_NOW),
    (80.0, Recommendation.STRONG),
    (70.0, Recommendation.WORTH_IT),
    (60.0, Recommendation.OPTIONAL),
    (0.0, Recommendation.SKIP),
]

CATEGORY_LABELS = {
    Recommendation.APPLY_NOW: ("🟢", "APLICAR YA"),
    Recommendation.STRONG: ("🟢", "MUY BUENA OPORTUNIDAD"),
    Recommendation.WORTH_IT: ("🟡", "VALE LA PENA"),
    Recommendation.OPTIONAL: ("🟠", "OPCIONAL"),
    Recommendation.SKIP: ("🔴", "NO RECOMENDADA"),
    Recommendation.NOT_ELIGIBLE: ("⚪", "NO ELEGIBLE"),
}


@dataclass
class CandidateContext:
    """Vista del perfil que necesita el scorer."""

    years_experience: float = 0.0
    degree_field: str = ""
    university: str = ""
    language_codes: dict[str, str] = field(default_factory=dict)   # {"de": "C1"}
    skills: list[str] = field(default_factory=list)
    role_families: list[str] = field(default_factory=list)
    excluded_areas: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)
    accepts_remote: bool = True
    accepts_hybrid: bool = True
    accepts_onsite: bool = True
    blocked_companies: list[str] = field(default_factory=list)
    favorite_companies: list[str] = field(default_factory=list)
    is_graduated: bool = True
    # "strict": sólo primer empleo real. "balanced": tolera algo de experiencia
    # deseable. "open": sin filtro extra.
    experience_policy: str = "strict"


@dataclass
class ScoreResult:
    fit_score: float = 0.0
    company_quality_score: float = 50.0
    career_value_score: float = 0.0
    german_advantage_score: float = 0.0
    location_score: float = 0.0
    recency_score: float = 0.0
    final_score: float = 0.0
    fit_breakdown: dict = field(default_factory=dict)
    boosts: list[dict] = field(default_factory=list)
    penalties: list[dict] = field(default_factory=list)
    eligible: bool = True
    not_eligible_reason: str | None = None
    recommendation: str = Recommendation.OPTIONAL.value
    match_reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    hard_blockers: list[str] = field(default_factory=list)
    summary: str = ""
    why_apply: str = ""
    confidence: float = 0.6

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Sub-scores
# --------------------------------------------------------------------------- #
def score_seniority(sen: SeniorityResult, exp: ExperienceRequirement,
                    candidate_years: float) -> tuple[float, list[str], list[str], list[str]]:
    """0-100 sobre compatibilidad de nivel. (score, razones, gaps, bloqueos)"""
    reasons: list[str] = []
    gaps: list[str] = []
    blockers: list[str] = []

    level = sen.level
    if level in (Seniority.SENIOR, Seniority.MANAGER, Seniority.DIRECTOR):
        blockers.append(f"posición de nivel {level.value}, fuera del alcance de un primer empleo")
        return 0.0, reasons, gaps, blockers
    if level == Seniority.SEMI_SENIOR:
        gaps.append("posición semi senior: requiere más recorrido del que tenés hoy")
        base = 25.0
    elif level in (Seniority.INTERNSHIP, Seniority.TRAINEE, Seniority.GRADUATE):
        base = 100.0
        reasons.append(f"posición {level.value}: diseñada para perfiles sin experiencia previa")
    elif level == Seniority.ENTRY_LEVEL:
        base = 98.0
        reasons.append("posición Entry Level")
    elif level == Seniority.JUNIOR:
        base = 90.0
        reasons.append("posición Junior")
    elif level == Seniority.JUNIOR_PLUS:
        base = 70.0
        reasons.append("posición junior con algo de experiencia deseada")
    else:
        base = 50.0
        gaps.append("el aviso no aclara el nivel de seniority")

    # Ajuste fino por años exigidos (§12)
    years = exp.min_years
    if exp.accepts_no_experience:
        base = max(base, 95.0)
        reasons.append("no requiere experiencia laboral previa")
    elif years is None:
        pass
    else:
        gap_years = max(0.0, years - candidate_years)
        if gap_years <= 0:
            base = max(base, 90.0)
            reasons.append(f"cumplís la experiencia pedida ({experience_bucket(exp)})")
        elif not exp.is_hard:
            # Preferencia, no filtro duro (§12, §51)
            penalty = min(22.0, gap_years * 8.0)
            base -= penalty
            gaps.append(f"pide {experience_bucket(exp)} como preferencia, no como requisito")
        else:
            if gap_years >= 3:
                blockers.append(f"exige {experience_bucket(exp)} de experiencia como requisito excluyente")
                return 0.0, reasons, gaps, blockers
            if gap_years >= 2:
                base = min(base, 28.0)
                gaps.append(f"exige {experience_bucket(exp)} como requisito: es un salto grande")
            else:
                base -= min(30.0, gap_years * 22.0)
                gaps.append(f"exige {experience_bucket(exp)} como requisito")

    if exp.mentions_students:
        base = min(100.0, base + 5.0)
        reasons.append("dirigida a estudiantes y recién graduados")

    return round(max(0.0, min(100.0, base)), 1), reasons, gaps, blockers


def score_education(text: str, candidate: CandidateContext) -> tuple[float, list[str], list[str], list[str]]:
    reasons: list[str] = []
    gaps: list[str] = []
    blockers: list[str] = []

    for blocker in EDUCATION_HARD_BLOCKERS:
        if has_term(text, blocker):
            blockers.append(f"requisito académico incompatible: '{blocker}'")
            return 0.0, reasons, gaps, blockers

    hits = found_terms(text, EDUCATION_BUSINESS_TERMS)
    field_hit = candidate.degree_field and searchable(candidate.degree_field) in text
    if field_hit:
        reasons.append(f"pide explícitamente {candidate.degree_field}")
        return 100.0, reasons, gaps, blockers
    if hits:
        score = min(100.0, 72.0 + 5.0 * len(hits))
        reasons.append(f"formación compatible: menciona {hits[0]}")
        return round(score, 1), reasons, gaps, blockers
    if contains_any(text, ("degree", "titulo", "graduado", "graduada")) or "universitari" in text:
        reasons.append("pide título universitario sin especificar carrera")
        return 78.0, reasons, gaps, blockers
    gaps.append("el aviso no detalla requisitos de formación")
    return 55.0, reasons, gaps, blockers


def score_languages(lang: LanguageAnalysis, candidate: CandidateContext
                    ) -> tuple[float, list[str], list[str], list[str]]:
    reasons: list[str] = []
    gaps: list[str] = []
    blockers: list[str] = []
    known = {code for code in candidate.language_codes}

    required = [l for l in lang.languages if l["requirement"] == "required"]
    preferred = [l for l in lang.languages if l["requirement"] == "preferred"]

    if not lang.languages:
        return 65.0, ["sin requisitos de idioma explícitos"], gaps, blockers

    score = 70.0
    for item in required:
        if item["code"] in known:
            score += 12.0
            reasons.append(f"{item['name']} requerido: lo cumplís")
        else:
            if item["code"] in ("pt", "fr", "it", "mandarin"):
                score -= 25.0
                gaps.append(f"pide {item['name']} y no figura en tu perfil")
            else:
                score -= 40.0
                blockers.append(f"requiere {item['name']} y no está en tu perfil")
    for item in preferred:
        if item["code"] in known:
            score += 8.0
            reasons.append(f"{item['name']} valorado: es una ventaja tuya")
        else:
            score -= 4.0
            gaps.append(f"{item['name']} deseable (no excluyente)")

    if lang.german_level in ("required", "valued") and "de" in known:
        reasons.append("tu alemán es una ventaja competitiva directa en esta búsqueda")

    return round(max(0.0, min(100.0, score)), 1), reasons, gaps, blockers


def score_skills(skills: SkillAnalysis, candidate: CandidateContext
                 ) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []
    gaps: list[str] = []
    owned = {s.lower() for s in candidate.skills}

    required = list(skills.must_have)
    optional = list(skills.should_have) + list(skills.nice_to_have)
    if not required and not optional:
        return 70.0, ["el aviso no lista herramientas específicas"], gaps

    matched = [s for s in required + optional if s in owned]
    if matched:
        reasons.append("tenés " + ", ".join(sorted(set(matched))[:4]))

    penalty = 0.0
    for skill in required:
        if skill not in owned:
            penalty += gap_severity(skill, "must") * 12.0
            gaps.append(f"pide {skill} (requisito)")
    for skill in skills.nice_to_have:
        if skill not in owned:
            penalty += gap_severity(skill, "nice") * 12.0
            gaps.append(f"{skill} deseable")
    for skill in skills.should_have:
        if skill not in owned:
            penalty += gap_severity(skill, "should") * 12.0

    score = 92.0 - penalty + min(12.0, 4.0 * len(matched))
    return round(max(0.0, min(100.0, score)), 1), reasons, gaps[:6]


def score_recency(publication_date: datetime | None, first_seen: datetime | None) -> float:
    reference = publication_date or first_seen
    if not reference:
        return 50.0
    age_days = max(0.0, (utcnow() - reference).total_seconds() / 86400.0)
    if age_days <= 1:
        return 100.0
    if age_days <= 3:
        return 92.0
    if age_days <= 7:
        return 82.0
    if age_days <= 14:
        return 68.0
    if age_days <= 30:
        return 50.0
    if age_days <= 60:
        return 30.0
    return 15.0


def score_career_value(company_quality: float, sen: SeniorityResult, role: RoleMatch,
                       lang: LanguageAnalysis, is_target: bool, text: str) -> tuple[float, list[str]]:
    """§16: ¿qué tan buen primer paso profesional es, más allá del fit?"""
    reasons: list[str] = []
    score = 0.45 * company_quality

    if sen.is_graduate_program:
        score += 16.0
        reasons.append("es un programa formal de graduados/trainees, pensado para formar")
    elif sen.level in (Seniority.INTERNSHIP, Seniority.TRAINEE):
        score += 10.0
        reasons.append("posición formativa con acompañamiento")
    elif sen.level in JUNIOR_FRIENDLY:
        score += 8.0

    if is_target:
        score += 8.0
        reasons.append("empresa objetivo: buena marca para el CV")

    if role.score >= 75 and not role.is_technical_heavy:
        score += 8.0
        reasons.append("el rol construye experiencia transferible a varias áreas")
    elif role.score >= 55:
        score += 4.0

    international = contains_any(text, ("global", "international", "latam", "regional",
                                        "multinational", "internacional", "regionales"))
    if international:
        score += 6.0
        reasons.append("exposición internacional / regional")

    if lang.german_level in ("required", "valued") or lang.requires_english:
        score += 5.0
        reasons.append("trabajo en entorno multilingüe")

    if contains_any(text, ("mentor", "training program", "plan de carrera", "capacitacion",
                           "desarrollo profesional", "learning budget",
                           "career path", "rotacion")):
        score += 7.0
        reasons.append("menciona formación / plan de carrera")

    return round(max(0.0, min(100.0, score)), 1), reasons


# --------------------------------------------------------------------------- #
# Score final
# --------------------------------------------------------------------------- #
def compute_scores(
    *,
    title: str,
    description: str | None,
    company_name: str,
    publication_date: datetime | None,
    first_seen: datetime | None,
    role: RoleMatch,
    sen: SeniorityResult,
    exp: ExperienceRequirement,
    lang: LanguageAnalysis,
    loc: LocationAnalysis,
    skills: SkillAnalysis,
    candidate: CandidateContext,
    company_quality: float,
    company_confidence: str,
    is_target_company: bool,
    salary_published: bool = False,
    fit_weights: dict | None = None,
    final_weights: dict | None = None,
    boosts_cfg: dict | None = None,
    penalties_cfg: dict | None = None,
) -> ScoreResult:
    fw = {**DEFAULT_FIT_WEIGHTS, **(fit_weights or {})}
    nw = {**DEFAULT_FINAL_WEIGHTS, **(final_weights or {})}
    bcfg = {**DEFAULT_BOOSTS, **(boosts_cfg or {})}
    pcfg = {**DEFAULT_PENALTIES, **(penalties_cfg or {})}

    text = searchable(title, description)
    result = ScoreResult()

    from app.pipeline.prefilter import TALENT_POOL_TERMS

    if contains_any(searchable(title), TALENT_POOL_TERMS):
        result.eligible = False
        result.not_eligible_reason = (
            "no es una búsqueda concreta (banco de talentos o feria de empleo)"
        )
    reasons: list[str] = []
    gaps: list[str] = []
    blockers: list[str] = []
    if not result.eligible and result.not_eligible_reason:
        blockers.append(result.not_eligible_reason)

    # ---- Elegibilidad dura ----
    if role.is_excluded:
        result.eligible = False
        result.not_eligible_reason = role.exclusion_reason
        blockers.append(role.exclusion_reason or "rol incompatible")
    elif role.score < ROLE_ELIGIBILITY_MIN:
        result.eligible = False
        result.not_eligible_reason = (
            f"el rol no tiene relación con tu perfil (compatibilidad {role.score:.0f}/100)"
        )
        blockers.append(result.not_eligible_reason)

    if searchable(company_name) in [searchable(c) for c in candidate.blocked_companies if c]:
        result.eligible = False
        result.not_eligible_reason = "empresa bloqueada en tu perfil"
        blockers.append("empresa bloqueada en tu perfil")

    # Política de experiencia: es el filtro que define el producto para un
    # primer empleo. Sin esto se cuelan "Experienced Associate" y puestos de 2-3 años.
    policy = EXPERIENCE_POLICY.get(candidate.experience_policy,
                                   EXPERIENCE_POLICY["strict"])
    if sen.level in policy["excluded_levels"]:
        result.eligible = False
        result.not_eligible_reason = (
            f"nivel {sen.level.value}: pide recorrido previo y buscás un primer empleo"
        )
        blockers.append(result.not_eligible_reason)
    elif exp.min_years and not exp.accepts_no_experience:
        gap = exp.min_years - candidate.years_experience
        limit = policy["max_hard_years"] if exp.is_hard else policy["max_soft_years"]
        if gap >= limit:
            kind = "exige" if exp.is_hard else "espera"
            result.eligible = False
            result.not_eligible_reason = (
                f"{kind} {experience_bucket(exp)} de experiencia y hoy tenés "
                f"{candidate.years_experience:g}"
            )
            blockers.append(result.not_eligible_reason)

    # §13: sólo estudiantes activos y la candidata ya está graduada
    if exp.enrolled_students_only and candidate.is_graduated:
        result.eligible = False
        result.not_eligible_reason = (
            "el aviso exige ser estudiante universitario en curso y vos ya estás graduada"
        )
        blockers.append(result.not_eligible_reason)

    # ---- Sub-scores ----
    sen_score, sen_reasons, sen_gaps, sen_blockers = score_seniority(sen, exp, candidate.years_experience)
    edu_score, edu_reasons, edu_gaps, edu_blockers = score_education(text, candidate)
    lang_score, lang_reasons, lang_gaps, lang_blockers = score_languages(lang, candidate)
    skill_score, skill_reasons, skill_gaps = score_skills(skills, candidate)

    reasons += role.evidence + sen_reasons + edu_reasons + lang_reasons + skill_reasons + loc.reasons
    gaps += sen_gaps + edu_gaps + lang_gaps + skill_gaps
    blockers += sen_blockers + edu_blockers + lang_blockers + loc.blockers

    other_score = 70.0
    if salary_published:
        other_score += 12.0
        reasons.append("publica rango salarial")
    if contains_any(text, LOW_QUALITY_SIGNALS):
        other_score = 10.0
    if sen.is_graduate_program:
        other_score = min(100.0, other_score + 15.0)

    breakdown = {
        "role": {"score": role.score, "weight": fw["role"], "points": role.score * fw["role"] / 100},
        "seniority": {"score": sen_score, "weight": fw["seniority"], "points": sen_score * fw["seniority"] / 100},
        "education": {"score": edu_score, "weight": fw["education"], "points": edu_score * fw["education"] / 100},
        "language": {"score": lang_score, "weight": fw["language"], "points": lang_score * fw["language"] / 100},
        "skills": {"score": skill_score, "weight": fw["skills"], "points": skill_score * fw["skills"] / 100},
        "location": {"score": loc.score, "weight": fw["location"], "points": loc.score * fw["location"] / 100},
        "other": {"score": other_score, "weight": fw["other"], "points": other_score * fw["other"] / 100},
    }
    total_weight = sum(fw.values()) or 100.0
    fit = sum(b["points"] for b in breakdown.values()) * (100.0 / total_weight)

    # Compuerta de rol (§21): las dimensiones neutras (educación, idioma, skills
    # sin datos) le dan un piso alto a cualquier aviso. Sin esta compuerta, un
    # puesto de psicólogo infantil llega a 57 sólo por no tener señales en contra.
    role_gate = ROLE_GATE_FLOOR + (1.0 - ROLE_GATE_FLOOR) * min(1.0, role.score / ROLE_GATE_FULL)
    fit *= role_gate
    breakdown["role_gate"] = {"score": round(role_gate * 100, 1), "weight": 0.0,
                              "points": 0.0, "nota": "multiplicador por compatibilidad de rol"}

    result.fit_score = round(max(0.0, min(100.0, fit)), 1)
    result.fit_breakdown = breakdown

    # ---- Otros indicadores ----
    result.german_advantage_score = lang.german_score
    result.location_score = loc.score
    result.company_quality_score = company_quality
    result.recency_score = score_recency(publication_date, first_seen)
    career, career_reasons = score_career_value(
        company_quality, sen, role, lang, is_target_company, text
    )
    result.career_value_score = career
    reasons += career_reasons

    # ---- Score final ponderado (§17) ----
    base_final = (
        nw["fit"] * result.fit_score
        + nw["company"] * result.company_quality_score
        + nw["career"] * result.career_value_score
        + nw["recency"] * result.recency_score
    ) / (sum(nw.values()) or 1.0)

    # ---- Boosts ----
    boosts: list[dict] = []
    # Lo que la candidata realmente busca: avisos que explícitamente no piden experiencia
    if exp.accepts_no_experience or exp.mentions_students or sen.is_graduate_program:
        label = ("no requiere experiencia previa" if exp.accepts_no_experience
                 else "dirigida a recién graduados")
        boosts.append({"key": "no_experience_required",
                       "points": bcfg["no_experience_required"],
                       "label": label.capitalize()})
    if lang.german_score >= 50 and "de" in candidate.language_codes:
        value = bcfg["german_advantage"] * (lang.german_score / 100.0)
        boosts.append({"key": "german_advantage", "points": round(value, 1),
                       "label": f"Alemán {lang.german_level} y vos lo hablás"})
    if is_target_company:
        boosts.append({"key": "target_company", "points": bcfg["target_company"],
                       "label": "Empresa objetivo"})
    if sen.is_graduate_program:
        boosts.append({"key": "graduate_program", "points": bcfg["graduate_program"],
                       "label": "Programa de graduados / jóvenes profesionales"})
    if sen.level == Seniority.INTERNSHIP and company_quality >= 78:
        boosts.append({"key": "premium_internship", "points": bcfg["premium_internship"],
                       "label": "Pasantía en empresa de primer nivel"})
    if lang.german_score >= 70 and is_target_company and sen.level in JUNIOR_FRIENDLY:
        boosts.append({"key": "rare_opportunity", "points": bcfg["rare_opportunity"],
                       "label": "Combinación poco frecuente: junior + alemán + empresa objetivo"})

    # ---- Penalizaciones ----
    penalties: list[dict] = []
    if exp.min_years and not exp.accepts_no_experience:
        gap = max(0.0, exp.min_years - candidate.years_experience)
        if gap > 0:
            points = min(pcfg["excess_experience"],
                         gap * policy["soft_penalty_per_year"] * (1.6 if exp.is_hard else 1.0))
            verb = "Exige" if exp.is_hard else "Prefiere"
            penalties.append({"key": "excess_experience", "points": round(points, 1),
                              "label": f"{verb} {experience_bucket(exp)} de experiencia"})
    if company_confidence == "LOW" and not is_target_company:
        penalties.append({"key": "unknown_company", "points": pcfg["unknown_company"],
                          "label": "Poca información verificable sobre la empresa"})
    if contains_any(text, LOW_QUALITY_SIGNALS):
        penalties.append({"key": "commission_only", "points": pcfg["commission_only"],
                          "label": "Señales de esquema 100% comisión / informal"})
        # Un esquema 100% comisión o multinivel no es un primer empleo válido (§17):
        # se descarta, no se penaliza y se muestra igual.
        result.eligible = False
        result.not_eligible_reason = (
            "el aviso presenta señales de trabajo informal, multinivel o 100% comisión"
        )
        blockers.append(result.not_eligible_reason)
    if not company_name.strip() or company_name.strip().lower() in ("confidential", "confidencial",
                                                                    "empresa confidencial", "n/a"):
        penalties.append({"key": "no_company", "points": pcfg["no_company"],
                          "label": "Oferta sin empresa identificada"})
    if role.score < 40:
        penalties.append({"key": "unrelated_role", "points": pcfg["unrelated_role"],
                          "label": "Rol poco relacionado con tu perfil"})
    if role.is_technical_heavy and sen.level not in (Seniority.INTERNSHIP, Seniority.TRAINEE):
        penalties.append({"key": "technical_heavy", "points": pcfg["technical_heavy"],
                          "label": "Posición técnica especializada"})
    if description and len(description) < 220:
        penalties.append({"key": "suspicious_description", "points": pcfg["suspicious_description"] / 2,
                          "label": "Descripción demasiado breve para evaluar bien"})

    final = base_final + sum(b["points"] for b in boosts) - sum(p["points"] for p in penalties)
    result.boosts = boosts
    result.penalties = penalties
    result.final_score = round(max(0.0, min(100.0, final)), 1)

    # ---- Elegibilidad / recomendación ----
    if blockers and any(b for b in (sen_blockers + edu_blockers + lang_blockers)):
        result.eligible = False
        result.not_eligible_reason = result.not_eligible_reason or blockers[0]

    # Si no sabemos el nivel, no se promete "aplicar ya": el sistema declara su
    # incertidumbre en vez de esconderla (§53).
    unknown_cap = policy.get("unknown_level_cap", 79.0)
    if sen.level == Seniority.UNKNOWN and result.final_score > unknown_cap:
        # Techo por incertidumbre, pero graduado: sin esto todos los avisos de
        # nivel desconocido empatan en el techo y el orden queda al azar.
        certainty = max(0.0, min(1.0, result.confidence))
        result.final_score = round(unknown_cap - 4.0 * (1.0 - certainty), 1)
        result.gaps.append("el aviso no aclara el nivel: revisá los requisitos antes de aplicar")

    if not result.eligible:
        result.recommendation = Recommendation.NOT_ELIGIBLE.value
        result.final_score = min(result.final_score, 45.0)
    else:
        for threshold, rec in RECOMMENDATION_BANDS:
            if result.final_score >= threshold:
                result.recommendation = rec.value
                break

    result.match_reasons = _dedupe_keep_order(reasons)[:10]
    result.gaps = _dedupe_keep_order(gaps)[:6]
    result.hard_blockers = _dedupe_keep_order(blockers)[:5]
    result.confidence = _confidence(sen, role, description, company_confidence)
    result.summary = _summary(title, company_name, sen, loc, exp)
    result.why_apply = _why_apply(result, sen, lang, is_target_company)
    return result


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _confidence(sen: SeniorityResult, role: RoleMatch, description: str | None,
                company_confidence: str) -> float:
    score = 0.35 * sen.confidence + 0.25 * min(1.0, role.score / 100.0)
    length = len(description or "")
    score += 0.25 * (1.0 if length > 1200 else 0.6 if length > 400 else 0.2)
    score += 0.15 * {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.25}.get(company_confidence, 0.25)
    return round(min(1.0, max(0.05, score)), 2)


def _summary(title: str, company: str, sen: SeniorityResult, loc: LocationAnalysis,
             exp: ExperienceRequirement) -> str:
    modality = {
        RemoteType.REMOTE: "remoto",
        RemoteType.HYBRID: "híbrido",
        RemoteType.ONSITE: "presencial",
        RemoteType.UNKNOWN: "modalidad sin especificar",
    }[loc.remote_type]
    where = loc.city.title() if loc.city else "ubicación no especificada"
    return (f"{title} en {company}. Nivel {sen.level.value}, {modality}, {where}. "
            f"Experiencia solicitada: {experience_bucket(exp)}.")


def _why_apply(result: ScoreResult, sen: SeniorityResult, lang: LanguageAnalysis,
               is_target: bool) -> str:
    if not result.eligible:
        return f"No aplicar: {result.not_eligible_reason}."
    rec = result.recommendation
    if rec == Recommendation.APPLY_NOW.value:
        head = "Aplicá hoy."
    elif rec == Recommendation.STRONG.value:
        head = "Muy buena oportunidad, aplicá."
    elif rec == Recommendation.WORTH_IT.value:
        head = "Vale la pena aplicar."
    elif rec == Recommendation.OPTIONAL.value:
        head = "Opcional: aplicá si tenés tiempo."
    else:
        head = "No es prioritaria."
    extras = []
    if sen.is_graduate_program:
        extras.append("es un programa pensado para tu momento de carrera")
    if lang.german_level in ("required", "valued"):
        extras.append("el alemán juega a tu favor acá")
    if is_target:
        extras.append("es una de tus empresas objetivo")
    if result.gaps:
        extras.append("los faltantes son deseables y no deberían frenar la postulación"
                      if not result.hard_blockers else "revisá los bloqueos antes de invertir tiempo")
    return head + (" " + "; ".join(extras).capitalize() + "." if extras else "")


def category_for(recommendation: str) -> tuple[str, str]:
    try:
        return CATEGORY_LABELS[Recommendation(recommendation)]
    except ValueError:
        return ("⚪", "SIN CATEGORÍA")
