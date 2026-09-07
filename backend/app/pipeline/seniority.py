"""Clasificación de seniority analizando el aviso completo (§11).

No confía en el título: "Business Analyst" con 5 años requeridos NO es junior.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.data.taxonomy import (
    ENTRY_TERMS,
    EXPERIENCED_TITLE_TERMS,
    GRADUATE_PROGRAM_TERMS,
    INTERNSHIP_TERMS,
    SEMI_SENIOR_TITLE_TERMS,
    SENIOR_FALSE_FRIENDS,
    SENIOR_TERMS,
)
from app.models import Seniority
from app.pipeline.experience import ExperienceRequirement
from app.pipeline.text import contains_any, found_terms, has_term, normalize_title, searchable

# Términos de management que sí implican jefatura (no "associate product manager")
MANAGEMENT_TERMS = ["head of", "director", "vp ", "vice president", "chief ",
                    "gerente", "jefe de", "c-level", "cto", "cfo", "ceo", "cmo"]

# Vocabulario de nivel que declaran los propios ATS. Es la señal más confiable
# que existe —la puso la empresa al publicar— y antes se descartaba.
ATS_LEVEL_MAP: dict[str, Seniority] = {
    # SmartRecruiters
    "internship": Seniority.INTERNSHIP,
    "student (high school)": Seniority.INTERNSHIP,
    "student (undergraduate/graduate)": Seniority.INTERNSHIP,
    "entry level": Seniority.ENTRY_LEVEL,
    "associate": Seniority.JUNIOR,
    "mid-senior level": Seniority.SEMI_SENIOR,
    "mid senior level": Seniority.SEMI_SENIOR,
    "director": Seniority.DIRECTOR,
    "executive": Seniority.DIRECTOR,
    # Jobicy / Himalayas / Eightfold
    "junior": Seniority.JUNIOR,
    "entry": Seniority.ENTRY_LEVEL,
    "entry-level": Seniority.ENTRY_LEVEL,
    "graduate": Seniority.GRADUATE,
    "mid": Seniority.SEMI_SENIOR,
    "midweight": Seniority.SEMI_SENIOR,
    "mid level": Seniority.SEMI_SENIOR,
    "mid-level": Seniority.SEMI_SENIOR,
    "senior": Seniority.SENIOR,
    "lead": Seniority.SENIOR,
    "manager": Seniority.MANAGER,
    "principal": Seniority.SENIOR,
    "expert": Seniority.SENIOR,
    # Lever / Ashby (commitment / employmentType)
    "intern": Seniority.INTERNSHIP,
    "trainee": Seniority.TRAINEE,
    "apprentice": Seniority.TRAINEE,
    "working student": Seniority.INTERNSHIP,
    "werkstudent": Seniority.INTERNSHIP,
}
# Valores que no dicen nada del nivel y hay que ignorar
ATS_LEVEL_NOISE = {
    "full-time", "fulltime", "full time", "part-time", "parttime", "part time",
    "permanent", "contract", "contractor", "temporary", "freelance", "regular",
    "not applicable", "any", "none", "n/a", "employee", "individual contributor",
    "ats", "other", "unspecified", "all levels", "varies",
}


def coerce_hint(hint) -> str:
    """Las fuentes mandan el nivel como texto, lista o None. Se normaliza a texto."""
    if hint is None:
        return ""
    if isinstance(hint, (list, tuple, set)):
        return ", ".join(str(x) for x in hint if x)
    return str(hint)


def level_from_ats(hint) -> Seniority | None:
    """Traduce el nivel declarado por la fuente al vocabulario propio."""
    hint = coerce_hint(hint)
    if not hint:
        return None
    for value in hint.split(","):
        value = value.strip().lower()
        if not value or value in ATS_LEVEL_NOISE:
            continue
        if value in ATS_LEVEL_MAP:
            return ATS_LEVEL_MAP[value]
    return None
MANAGER_TERMS = ["manager", "supervisor", "team lead", "tech lead", "coordinador",
                 "coordinadora", "responsable de"]


@dataclass
class SeniorityResult:
    level: Seniority
    confidence: float
    signals: list[str] = field(default_factory=list)
    is_graduate_program: bool = False
    is_internship: bool = False


def _title_has(title: str, terms) -> list[str]:
    return found_terms(title, terms)


def classify_seniority(
    title: str | None,
    description: str | None,
    experience: ExperienceRequirement,
    source_hint=None,
) -> SeniorityResult:
    norm_title = normalize_title(title)
    text = searchable(title, description)
    source_hint = coerce_hint(source_hint) or None
    hint = (source_hint or "").lower()
    signals: list[str] = []
    ats_level = level_from_ats(source_hint)

    # Sólo el título define una pasantía: la palabra "intern" en el cuerpo suele
    # venir de "internal" o "international".
    is_internship = bool(_title_has(norm_title, INTERNSHIP_TERMS))
    is_grad = contains_any(text, GRADUATE_PROGRAM_TERMS)
    if is_grad:
        signals.append("menciona programa de graduados / jóvenes profesionales")

    # 0) Un nivel de dirección declarado por la fuente es tan válido como el título
    if ats_level in (Seniority.DIRECTOR, Seniority.MANAGER):
        return SeniorityResult(ats_level, 0.85,
                               [f"la empresa lo publicó como '{source_hint}'"],
                               is_grad, False)

    # 1) Señales duras de exclusión: management real
    if contains_any(norm_title, MANAGEMENT_TERMS):
        return SeniorityResult(Seniority.DIRECTOR, 0.95, ["título de dirección"], is_grad, is_internship)

    false_friend = contains_any(norm_title, SENIOR_FALSE_FRIENDS)
    if not false_friend and contains_any(norm_title, MANAGER_TERMS):
        return SeniorityResult(Seniority.MANAGER, 0.85, ["título de jefatura"], is_grad, is_internship)

    # "Experienced Associate" / "Managing Consultant": el título dice explícitamente
    # que NO es un primer empleo, aunque contenga "associate" o "consultant".
    experienced_hit = found_terms(norm_title, EXPERIENCED_TITLE_TERMS)
    if experienced_hit and not false_friend:
        return SeniorityResult(
            Seniority.SEMI_SENIOR, 0.88,
            [f"el título dice '{experienced_hit[0].strip()}': pide recorrido previo"],
            is_grad, is_internship,
        )
    semi_hit = found_terms(norm_title, SEMI_SENIOR_TITLE_TERMS)
    if semi_hit and not false_friend:
        return SeniorityResult(
            Seniority.SEMI_SENIOR, 0.82,
            [f"'{semi_hit[0].strip()}' es un nivel por encima de un primer empleo"],
            is_grad, is_internship,
        )

    senior_in_title = [t for t in _title_has(norm_title, SENIOR_TERMS) if t.strip() not in
                       ("manager", "coordinador", "coordinadora", "supervisor")]
    if senior_in_title and not false_friend:
        if "semi senior" in norm_title or "ssr" in norm_title:
            return SeniorityResult(Seniority.SEMI_SENIOR, 0.9, ["título semi senior"], is_grad, is_internship)
        return SeniorityResult(Seniority.SENIOR, 0.92,
                               [f"título contiene '{senior_in_title[0].strip()}'"], is_grad, is_internship)

    # 2) La experiencia exigida manda por sobre el título
    years = experience.min_years
    if experience.is_hard and years is not None:
        if years >= 5:
            return SeniorityResult(Seniority.SENIOR, 0.9,
                                   [f"exige {years:g}+ años de experiencia"], is_grad, is_internship)
        if years >= 3:
            return SeniorityResult(Seniority.SEMI_SENIOR, 0.85,
                                   [f"exige {years:g}+ años de experiencia"], is_grad, is_internship)

    # 3) Señales de entrada
    if is_internship:
        signals.append("pasantía / internship")
        return SeniorityResult(Seniority.INTERNSHIP, 0.9, signals, is_grad, True)

    if has_term(norm_title, "trainee") or has_term(hint, "trainee"):
        signals.append("posición de trainee")
        return SeniorityResult(Seniority.TRAINEE, 0.9, signals, is_grad, False)

    if is_grad or has_term(norm_title, "graduate") or has_term(norm_title, "new grad"):
        signals.append("orientada a graduados recientes")
        return SeniorityResult(Seniority.GRADUATE, 0.85, signals, True, False)

    entry_in_title = found_terms(norm_title, ENTRY_TERMS)
    if entry_in_title:
        signals.append(f"título indica nivel inicial ('{entry_in_title[0].strip()}')")
        level = Seniority.JUNIOR if has_term(norm_title, "junior") else Seniority.ENTRY_LEVEL
        return SeniorityResult(level, 0.85, signals, is_grad, False)

    if experience.accepts_no_experience:
        signals.append("no requiere experiencia previa")
        return SeniorityResult(Seniority.ENTRY_LEVEL, 0.8, signals, is_grad, False)

    if experience.mentions_students:
        signals.append("dirigida a estudiantes / recién graduados")
        return SeniorityResult(Seniority.GRADUATE, 0.8, signals, is_grad, False)

    if years is not None:
        if years <= 1:
            signals.append(f"pide ~{years:g} año(s) de experiencia")
            return SeniorityResult(Seniority.JUNIOR, 0.75, signals, is_grad, False)
        if years <= 2:
            signals.append(f"pide ~{years:g} años de experiencia")
            return SeniorityResult(Seniority.JUNIOR_PLUS, 0.7, signals, is_grad, False)
        if years <= 4:
            signals.append(f"pide ~{years:g} años de experiencia")
            return SeniorityResult(Seniority.SEMI_SENIOR, 0.75, signals, is_grad, False)
        signals.append(f"pide {years:g}+ años de experiencia")
        return SeniorityResult(Seniority.SENIOR, 0.8, signals, is_grad, False)

    # 4) Señales textuales de nivel inicial en el cuerpo
    body_entry = found_terms(text, ENTRY_TERMS)
    if body_entry:
        signals.append(f"la descripción menciona '{body_entry[0].strip()}'")
        return SeniorityResult(Seniority.ENTRY_LEVEL, 0.6, signals, is_grad, False)

    # Último recurso antes de rendirse: el nivel que declaró la propia empresa
    if ats_level is not None:
        signals.append(f"la empresa publicó el aviso como nivel '{source_hint}'")
        return SeniorityResult(ats_level, 0.7, signals, is_grad,
                               ats_level == Seniority.INTERNSHIP)

    signals.append("sin señales claras de nivel")
    return SeniorityResult(Seniority.UNKNOWN, 0.35, signals, is_grad, False)
