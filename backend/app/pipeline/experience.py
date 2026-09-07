"""Extracción de requisitos de experiencia (§12).

Distingue explícitamente requisito duro ("minimum 2 years required") de
preferencia ("2 years preferred"), que es la diferencia que el brief marca como
fundamental: las preferencias NO se convierten en filtros duros.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.pipeline.text import searchable, sentences

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "ein": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4, "fuenf": 5, "funf": 5,
}

_NUM = r"(\d{1,2}|" + "|".join(WORD_NUMBERS) + r")"

RANGE_PATTERNS = [
    re.compile(rf"{_NUM}\s*(?:-|–|a|to|hasta|bis)\s*{_NUM}\s*\+?\s*(?:years?|yrs?|anos?|años?|jahre)", re.I),
]
SINGLE_PATTERNS = [
    re.compile(rf"(?:at least|minimum(?: of)?|min\.?|m[ií]nimo(?: de)?|al menos|mindestens)\s*{_NUM}\s*\+?\s*(?:years?|yrs?|anos?|años?|jahre)", re.I),
    re.compile(rf"{_NUM}\s*\+\s*(?:years?|yrs?|anos?|años?|jahre)", re.I),
    # "3 years of sales experience", "2 años de experiencia en marketing"
    re.compile(rf"{_NUM}\s*\+?\s*(?:years?|yrs?|anos?|años?|jahre)\b[^.\n]{{0,45}}?(?:experien|erfahrung)", re.I),
    re.compile(rf"(?:experien\w*|erfahrung)[^.\n]{{0,40}}?{_NUM}\s*\+?\s*(?:years?|yrs?|anos?|años?|jahre)", re.I),
]
MONTH_PATTERNS = [
    re.compile(rf"{_NUM}\s*(?:-|–|a|to)?\s*(?:\d{{1,2}})?\s*(?:months?|meses|monate)\s*(?:of|de)?\s*(?:experien|erfahrung|practica|pasant)", re.I),
]

ZERO_EXPERIENCE_MARKERS = [
    "no experience required", "no experience necessary", "no prior experience",
    "sin experiencia previa", "sin experiencia laboral", "no se requiere experiencia",
    "no requiere experiencia", "experiencia no excluyente", "sin experiencia",
    "0 years", "zero experience", "keine berufserfahrung", "ohne berufserfahrung",
    "we do not require experience", "first professional experience",
    "primera experiencia laboral", "primer empleo", "erste berufserfahrung",
    "entry level position", "no experience needed",
]

STUDENT_GRADUATE_MARKERS = [
    "students or recent graduates", "students and recent graduates",
    "recent graduates", "recently graduated", "recién graduados", "recien graduados",
    "próximos a graduarse", "proximos a graduarse", "estudiantes avanzados",
    "estudiantes universitarios", "final year students", "graduating students",
    "new graduates", "new grads", "graduates of any discipline", "absolventen",
    "studierende", "graduados recientes", "jóvenes profesionales", "jovenes profesionales",
]

ENROLLED_ONLY_MARKERS = [
    "must be currently enrolled", "currently enrolled student",
    "actively enrolled", "debe ser estudiante regular", "alumno regular",
    "estudiante regular", "must be enrolled in a degree program",
    "eingeschriebene studierende", "immatrikuliert",
    "students only", "only current students", "estudiantes exclusivamente",
    "debes ser estudiante", "ser estudiante activo", "cursando actualmente",
    "con al menos 2 años de cursada restantes", "certificado de alumno regular",
]

HARD_MARKERS = [
    "required", "requerido", "requerida", "excluyente", "obligatorio", "obligatoria",
    "mandatory", "must have", "es requisito", "requisito excluyente", "imprescindible",
    "zwingend", "voraussetzung", "minimum", "minimo", "minima", "at least", "al menos",
    "se requiere", "necesario contar con", "debe contar con", "must possess",
]
# "2 años de cursada", "3 años de carrera": no es experiencia laboral.
NON_EXPERIENCE_CONTEXT = re.compile(
    r"(cursad[ao]|carrera|estudios?|materias|restantes|de la licenciatura|"
    r"studium|semester|degree program|of study|academic)",
    re.I,
)

SOFT_MARKERS = [
    "preferred", "preferible", "deseable", "nice to have", "a plus", "es un plus",
    "valorado", "se valorará", "se valorara", "wünschenswert", "wunschenswert",
    "von vorteil", "ideally", "idealmente", "bonus", "not required", "no excluyente",
    "would be nice", "advantage", "ventaja",
]


@dataclass
class ExperienceRequirement:
    min_years: float | None = None
    max_years: float | None = None
    is_hard: bool = False
    accepts_no_experience: bool = False
    mentions_students: bool = False
    enrolled_students_only: bool = False
    evidence: list[str] = field(default_factory=list)


def _to_num(token: str) -> float | None:
    token = token.strip().lower()
    if token.isdigit():
        return float(token)
    return float(WORD_NUMBERS[token]) if token in WORD_NUMBERS else None


def _classify_hardness(sentence: str) -> bool | None:
    """True=duro, False=preferencia, None=indeterminado."""
    low = sentence.lower()
    soft = any(m in low for m in SOFT_MARKERS)
    hard = any(m in low for m in HARD_MARKERS)
    if soft and not hard:
        return False
    if soft and hard:
        # "minimum 2 years preferred" -> la preferencia manda
        return False
    if hard:
        return True
    return None


def parse_experience(title: str | None, description: str | None) -> ExperienceRequirement:
    text = searchable(title, description)
    req = ExperienceRequirement()

    if any(m in text for m in ZERO_EXPERIENCE_MARKERS):
        req.accepts_no_experience = True
        req.min_years = 0.0
        req.evidence.append("menciona explícitamente que no requiere experiencia previa")
    if any(m in text for m in STUDENT_GRADUATE_MARKERS):
        req.mentions_students = True
        req.evidence.append("dirigido a estudiantes / recién graduados")
    if any(m in text for m in ENROLLED_ONLY_MARKERS):
        req.enrolled_students_only = True
        req.evidence.append("pide estudiante actualmente cursando")

    candidates: list[tuple[float, float | None, bool | None, str]] = []
    sents = sentences(searchable(title, description))
    for idx, sent in enumerate(sents):
        # La marca de dureza suele caer en la frase siguiente ("... 3 años. Excluyente.")
        window = " ".join(sents[idx : idx + 2])
        if NON_EXPERIENCE_CONTEXT.search(sent):
            continue
        for pattern in RANGE_PATTERNS:
            for m in pattern.finditer(sent):
                lo, hi = _to_num(m.group(1)), _to_num(m.group(2))
                if lo is not None:
                    candidates.append((lo, hi, _classify_hardness(window), sent[:220]))
        if any(p.search(sent) for p in RANGE_PATTERNS):
            continue
        for pattern in SINGLE_PATTERNS:
            m = pattern.search(sent)
            if m:
                val = _to_num(m.group(1))
                if val is not None:
                    candidates.append((val, None, _classify_hardness(window), sent[:220]))
                break
        for pattern in MONTH_PATTERNS:
            m = pattern.search(sent)
            if m:
                val = _to_num(m.group(1))
                if val is not None and val <= 24:
                    candidates.append((val / 12.0, None, _classify_hardness(window), sent[:220]))
                break

    if candidates:
        hard = [c for c in candidates if c[2] is True]
        pool = hard or candidates
        # El requisito relevante es el mínimo exigido más bajo entre los duros.
        lo, hi, hardness, evidence = min(pool, key=lambda c: c[0])
        req.min_years = lo if req.min_years is None else min(req.min_years, lo)
        req.max_years = hi
        req.is_hard = bool(hard) and hardness is True
        req.evidence.append(evidence)

    if req.accepts_no_experience:
        req.is_hard = False
        req.min_years = 0.0
    return req


def experience_bucket(req: ExperienceRequirement) -> str:
    """Etiqueta legible para la UI."""
    if req.accepts_no_experience or (req.min_years is not None and req.min_years <= 0):
        return "Sin experiencia"
    if req.min_years is None:
        return "No especificada"
    lo = req.min_years
    hi = req.max_years
    if hi and hi > lo:
        return f"{lo:g}-{hi:g} años"
    if lo < 1:
        return f"{int(lo * 12)} meses"
    return f"{lo:g}+ años"
