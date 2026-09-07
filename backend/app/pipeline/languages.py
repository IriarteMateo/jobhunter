"""Detección de idiomas y german_advantage_score (§4)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.data.taxonomy import (
    ENGLISH_TERMS,
    GERMAN_DESIRABLE_MARKERS,
    GERMAN_REQUIRED_MARKERS,
    GERMAN_TERMS,
    GERMAN_VALUED_MARKERS,
    OTHER_LANGUAGE_TERMS,
    PORTUGUESE_TERMS,
    SPANISH_TERMS,
)
from app.data.locations import DACH_MARKERS
from app.pipeline.text import contains_any, has_term, searchable, sentences

GERMAN_LEVELS = {
    "none": 0.0,
    "context": 35.0,      # sólo contexto DACH / mercado alemán
    "desirable": 50.0,
    "valued": 70.0,
    "required": 100.0,
}


@dataclass
class LanguageAnalysis:
    languages: list[dict] = field(default_factory=list)   # [{code, name, requirement}]
    german_level: str = "none"
    german_score: float = 0.0
    german_evidence: list[str] = field(default_factory=list)
    requires_english: bool = False
    requires_portuguese: bool = False


# "not required", "no excluyente": la negación invierte el sentido y hay que
# detectarla ANTES que la marca positiva que contiene.
NEGATED_REQUIREMENT = [
    "not required", "not mandatory", "not a requirement", "no required",
    "no excluyente", "no es excluyente", "no requerido", "no obligatorio",
    "nicht erforderlich", "kein muss", "not strictly required", "not needed",
    "no es requisito", "sin ser excluyente",
]


def _requirement_of(sentence: str) -> str:
    low = sentence
    if any(m in low for m in NEGATED_REQUIREMENT):
        return "preferred"
    if any(m in low for m in ("required", "excluyente", "obligatori", "must ", "fluent",
                              "native", "imprescindible", "requerido", "requerida",
                              "se requiere", "requiere ", "erforderlich", "nivel avanzado",
                              "avanzado excluyente", "muttersprache")):
        return "required"
    if any(m in low for m in ("preferred", "deseable", "a plus", "plus", "nice to have",
                              "valorado", "advantage", "ventaja", "wunschenswert",
                              "von vorteil", "no excluyente")):
        return "preferred"
    return "mentioned"


def analyze_languages(title: str | None, description: str | None) -> LanguageAnalysis:
    text = searchable(title, description)
    result = LanguageAnalysis()

    def add(code: str, name: str, terms: list[str]) -> None:
        hits = [s for s in sentences(text) if contains_any(s, terms)]
        if not hits:
            return
        requirement = "mentioned"
        for sent in hits:
            req = _requirement_of(sent)
            if req == "required":
                requirement = "required"
                break
            if req == "preferred":
                requirement = "preferred"
        result.languages.append({"code": code, "name": name, "requirement": requirement,
                                 "evidence": hits[0][:200]})

    add("en", "Inglés", ENGLISH_TERMS)
    add("es", "Español", SPANISH_TERMS)
    add("pt", "Portugués", PORTUGUESE_TERMS)
    for code, terms in OTHER_LANGUAGE_TERMS.items():
        add(code, code.capitalize(), terms)

    result.requires_english = any(
        l["code"] == "en" and l["requirement"] == "required" for l in result.languages
    )
    result.requires_portuguese = any(
        l["code"] == "pt" and l["requirement"] == "required" for l in result.languages
    )

    # --- Alemán ---
    level = "none"
    evidence: list[str] = []
    if contains_any(text, GERMAN_REQUIRED_MARKERS):
        level = "required"
    elif contains_any(text, GERMAN_VALUED_MARKERS):
        level = "valued"
    elif contains_any(text, GERMAN_DESIRABLE_MARKERS):
        level = "desirable"
    elif contains_any(text, GERMAN_TERMS):
        # Distinguir "German" como idioma de "Germany" como país
        german_sents = [s for s in sentences(text) if contains_any(s, GERMAN_TERMS)]
        evidence = german_sents[:2]
        language_context = any(
            contains_any(s, ("language", "speak", "idioma", "fluent", "level",
                             "kenntnisse", "sprache", "nivel", "bilingual"))
            for s in german_sents
        )
        dach_context = contains_any(text, DACH_MARKERS)
        if language_context:
            level = "valued"
        elif dach_context:
            level = "context"
        else:
            level = "desirable"

    if level != "none" and not evidence:
        evidence = [s[:200] for s in sentences(text)
                    if contains_any(s, GERMAN_TERMS)][:2]

    result.german_level = level
    result.german_score = GERMAN_LEVELS[level]
    result.german_evidence = evidence

    if level != "none" and not any(l["code"] == "de" for l in result.languages):
        requirement = {"required": "required", "valued": "preferred",
                       "desirable": "preferred", "context": "mentioned"}[level]
        result.languages.append({"code": "de", "name": "Alemán", "requirement": requirement,
                                 "evidence": (evidence[0] if evidence else "")[:200]})
    return result
