"""Carga de CV en PDF y extracción de campos (§33).

Lo extraído es una PROPUESTA: el perfil generado siempre queda editable y se
devuelve marcado como sugerencia, nunca se pisa el perfil en silencio.
"""
from __future__ import annotations

import io
import re

from pypdf import PdfReader

from app.data.taxonomy import KNOWN_SKILLS
from app.pipeline.text import has_term, searchable

LANGUAGE_PATTERNS = {
    "es": ["español", "espanol", "castellano", "spanish"],
    "en": ["inglés", "ingles", "english"],
    "de": ["alemán", "aleman", "german", "deutsch"],
    "pt": ["portugués", "portugues", "portuguese"],
    "fr": ["francés", "frances", "french"],
    "it": ["italiano", "italian"],
}
LEVEL_PATTERNS = [
    (r"\b(nativo|native|muttersprache)\b", "Nativo"),
    (r"\b(c2|bilingüe|bilingue|bilingual)\b", "C2 / Bilingüe"),
    (r"\b(c1|avanzado|advanced|fließend)\b", "C1 / Avanzado"),
    (r"\b(b2|intermedio alto|upper intermediate)\b", "B2"),
    (r"\b(b1|intermedio|intermediate)\b", "B1"),
    (r"\b(a1|a2|básico|basico|basic)\b", "Básico"),
]
UNIVERSITY_PATTERN = re.compile(
    r"(universidad[^\n,;]{0,60}|university[^\n,;]{0,60}|udesa|utdt|uba|itba|austral)", re.I
)
DEGREE_PATTERN = re.compile(
    r"(licenciatura[^\n,;]{0,60}|ingenier[íi]a[^\n,;]{0,60}|bachelor[^\n,;]{0,60}|"
    r"contador[^\n,;]{0,40}|abogac[íi]a|master[^\n,;]{0,50})", re.I
)
YEAR_PATTERN = re.compile(r"\b(20[0-3]\d)\b")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def extract_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_cv(text: str) -> dict:
    """Devuelve una propuesta de perfil. Nada se aplica automáticamente."""
    low = searchable(text)

    languages = []
    for code, terms in LANGUAGE_PATTERNS.items():
        for term in terms:
            if not has_term(low, term):
                continue
            idx = low.find(term)
            window = low[idx: idx + 90]
            level = next((label for pattern, label in LEVEL_PATTERNS
                          if re.search(pattern, window, re.I)), "")
            languages.append({"code": code, "name": term.capitalize(), "level": level})
            break

    skills = sorted({s for s in KNOWN_SKILLS if has_term(low, s)})
    university = (UNIVERSITY_PATTERN.search(text) or [None])
    degree = (DEGREE_PATTERN.search(text) or [None])
    years = [int(y) for y in YEAR_PATTERN.findall(text)]
    email = EMAIL_PATTERN.search(text)

    return {
        "university": university.group(0).strip() if hasattr(university, "group") else "",
        "degree": degree.group(0).strip() if hasattr(degree, "group") else "",
        "graduation_year": max(years) if years else None,
        "languages": languages,
        "skills": skills,
        "email": email.group(0) if email else None,
        "chars": len(text),
        "nota": "Propuesta extraída del CV. Revisá y corregí antes de guardar.",
    }
