"""Extracción de skills y clasificación MUST / SHOULD / NICE (§51)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.data.taxonomy import KNOWN_SKILLS, SOFT_GAP_SKILLS
from app.pipeline.text import clean_text, searchable, sentences

MUST_MARKERS = [
    "required", "requerido", "requerida", "excluyente", "obligatorio", "must have",
    "must be", "imprescindible", "es requisito", "se requiere", "necesario",
    "requirements", "requisitos", "zwingend", "voraussetzung", "erforderlich",
    "qualifications", "what you need", "lo que necesitas", "buscamos que",
]
NICE_MARKERS = [
    "nice to have", "a plus", "es un plus", "deseable", "preferred", "preferible",
    "valorado", "se valorara", "bonus", "wunschenswert", "von vorteil", "ideally",
    "no excluyente", "opcional", "would be great", "extra credit", "diferencial",
]

REQUIREMENT_HEADINGS = re.compile(
    r"^(requisitos|requirements|qualifications|what you.ll need|what we.re looking for|"
    r"lo que buscamos|perfil|tu perfil|dein profil|anforderungen|must have|"
    r"skills|competencias|experiencia requerida)\b",
    re.I,
)
PREFERRED_HEADINGS = re.compile(
    r"^(deseable|nice to have|preferred|plus|bonus|se valorar|wunschenswert|"
    r"nice-to-have|opcional|diferenciales?)\b",
    re.I,
)


@dataclass
class SkillAnalysis:
    skills: list[str] = field(default_factory=list)
    must_have: list[str] = field(default_factory=list)
    should_have: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    preferred_requirements: list[str] = field(default_factory=list)


def _bucket_for(sentence: str) -> str:
    low = sentence.lower()
    if any(m in low for m in NICE_MARKERS):
        return "nice"
    if any(m in low for m in MUST_MARKERS):
        return "must"
    return "should"


def extract_skills(title: str | None, description: str | None) -> SkillAnalysis:
    result = SkillAnalysis()
    if not description:
        text = searchable(title)
        result.skills = sorted({s for s in KNOWN_SKILLS if _skill_in(text, s)})
        result.should_have = list(result.skills)
        return result

    text = searchable(title, description)
    result.skills = sorted({s for s in KNOWN_SKILLS if _skill_in(text, s)})

    # Recorre el aviso siguiendo los encabezados de secciones.
    section = "should"
    for raw_line in (description or "").splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        if PREFERRED_HEADINGS.match(line):
            section = "nice"
            continue
        if REQUIREMENT_HEADINGS.match(line):
            section = "must"
            continue
        if len(line) < 8 or len(line) > 400:
            continue
        low = searchable(line)
        bucket = _bucket_for(low)
        if bucket == "should":
            bucket = section
        if bucket == "nice":
            result.preferred_requirements.append(line)
        elif bucket == "must":
            result.requirements.append(line)

        for skill in KNOWN_SKILLS:
            if not _skill_in(low, skill):
                continue
            target = {"must": result.must_have, "nice": result.nice_to_have,
                      "should": result.should_have}[bucket]
            if skill not in target:
                target.append(skill)

    # Un skill listado como must Y como nice cuenta como nice (§51: la más laxa gana)
    result.must_have = [s for s in result.must_have if s not in result.nice_to_have]
    result.should_have = [s for s in result.should_have
                          if s not in result.must_have and s not in result.nice_to_have]
    result.requirements = result.requirements[:25]
    result.preferred_requirements = result.preferred_requirements[:15]
    return result


def _skill_in(text: str, skill: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(skill)}(?![a-z0-9])", text) is not None


def gap_severity(skill: str, bucket: str) -> float:
    """Penalización por skill faltante. Los técnicos aprendibles pesan poco (§51)."""
    if bucket == "nice":
        return 0.3
    base = 1.0 if bucket == "must" else 0.6
    if skill in SOFT_GAP_SKILLS:
        base *= 0.45
    return base
