"""Utilidades de texto compartidas por el pipeline."""
from __future__ import annotations

import hashlib
import re
import unicodedata

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)

COMPANY_SUFFIXES = {
    "sa", "s a", "srl", "s r l", "sas", "inc", "inc.", "llc", "ltd", "ltda",
    "limited", "gmbh", "ag", "plc", "corp", "corporation", "company", "co",
    "argentina", "arg", "latam", "group", "grupo", "holding", "holdings",
    "technologies", "technology", "solutions", "services", "consulting",
    "sociedad anonima", "s.a.", "s.r.l.",
}


def strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)
    )


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return _WS.sub(" ", value).strip()


def slugify(value: str) -> str:
    value = strip_accents((value or "").lower())
    value = _PUNCT.sub(" ", value)
    return _WS.sub("-", value).strip("-")


def normalize_company(name: str | None) -> str:
    """'EBANX Argentina S.A.' -> 'ebanx'."""
    base = strip_accents((name or "").lower())
    base = base.replace("&", " and ")
    base = _PUNCT.sub(" ", base)
    tokens = [t for t in base.split() if t]
    # "EBANX S.A." -> tokens [ebanx, s, a]: se descartan sufijos y letras sueltas finales
    while tokens and (tokens[-1] in COMPANY_SUFFIXES or len(tokens[-1]) == 1):
        tokens.pop()
    if not tokens:
        tokens = [t for t in base.split() if t]
    return " ".join(tokens).strip()


TITLE_NOISE = [
    r"\((remote|hybrid|on-?site|presencial|h[ií]brido|remoto)\)",
    r"\b(m/f/d|m/w/d|f/m/d|w/m/d|m/f/x|all genders|todos los g[eé]neros)\b",
    r"\((full[- ]?time|part[- ]?time|tiempo completo|medio tiempo)\)",
    r"\b(req(uisition)?\s*#?\s*\d+)\b",
    r"[-–—|,]\s*(argentina|buenos aires|caba|latam|remote|remoto)\s*$",
]


def normalize_title(title: str | None) -> str:
    value = strip_accents((title or "").lower())
    for pattern in TITLE_NOISE:
        value = re.sub(pattern, " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\bsr\.?\b", "senior", value)
    value = re.sub(r"\bjr\.?\b", "junior", value)
    value = re.sub(r"\bssr\.?\b", "semi senior", value)
    value = _PUNCT.sub(" ", value)
    return _WS.sub(" ", value).strip()


def content_hash(*parts: str | None) -> str:
    payload = "|".join(clean_text(p).lower() for p in parts if p)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def description_hash(description: str | None) -> str:
    """Hash tolerante a cambios menores de formato (para detectar reposts)."""
    text = strip_accents((description or "").lower())
    text = _PUNCT.sub(" ", text)
    tokens = _WS.sub(" ", text).strip().split()
    return hashlib.sha256(" ".join(tokens[:400]).encode("utf-8")).hexdigest()[:32]


_TERM_CACHE: dict[str, re.Pattern] = {}


def term_pattern(term: str) -> re.Pattern:
    """Patrón con límites de palabra.

    Sin esto, "intern" matchea dentro de "international" y clasifica una
    posición senior como pasantía. Los límites sólo se aplican donde el borde
    del término es alfanumérico, para que "jr." o "sr " sigan funcionando.
    """
    cached = _TERM_CACHE.get(term)
    if cached is not None:
        return cached
    escaped = re.escape(term.strip())
    left = r"(?<![a-z0-9])" if term.strip()[:1].isalnum() else ""
    right = r"(?![a-z0-9])" if term.strip()[-1:].isalnum() else ""
    pattern = re.compile(left + escaped + right, re.IGNORECASE)
    _TERM_CACHE[term] = pattern
    return pattern


def has_term(haystack: str, term: str) -> bool:
    return term_pattern(term).search(haystack) is not None


def contains_any(haystack: str, needles) -> bool:
    return any(has_term(haystack, n) for n in needles)


def found_terms(haystack: str, needles) -> list[str]:
    return [n for n in needles if has_term(haystack, n)]


def searchable(*parts: str | None) -> str:
    """Texto en minúsculas y sin acentos para búsqueda de términos."""
    joined = " \n ".join(p for p in parts if p)
    return strip_accents(joined.lower())


def sentences(text: str) -> list[str]:
    raw = re.split(r"[\n\r]+|(?<=[.;!?])\s+|•|·|•", text or "")
    return [clean_text(s) for s in raw if clean_text(s)]
