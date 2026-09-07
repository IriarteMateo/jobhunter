"""Compatibilidad de rol: evita falsos negativos (§20) y falsos positivos (§21).

No alcanza con keywords: "Strategy & Operations Analyst" tiene que reconocerse
compatible con Negocios Digitales, y "Senior Product Manager" tiene que
descartarse aunque contenga la palabra "product".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.data.taxonomy import (
    EXCLUDED_ROLE_TERMS,
    ROLE_FAMILIES,
    TECHNICAL_HEAVY_TERMS,
)
from app.pipeline.text import has_term, normalize_title, searchable

STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "y", "and", "or", "o", "for", "in", "en",
    "a", "the", "of", "con", "para", "un", "una", "at", "to", "-", "&",
}

# Tokens que aparecen en casi cualquier título y no distinguen un rol de otro.
# Sin esta distinción, "Analista de Mantenimiento" matchea "Analista de Datos"
# sólo por compartir "analista".
GENERIC_TOKENS = {
    "analista", "analyst", "analytics", "especialista", "specialist", "junior",
    "jr", "senior", "sr", "associate", "assistant", "asistente", "auxiliar",
    "coordinator", "coordinador", "coordinadora", "manager", "gerente", "trainee",
    "intern", "pasante", "graduate", "entry", "level", "profesional", "professional",
    "consultant", "consultor", "consultora", "responsable", "officer", "executive",
}


def _tokens(value: str) -> set[str]:
    return {t for t in normalize_title(value).split() if t and t not in STOPWORDS}


@dataclass
class RoleMatch:
    family: str | None = None
    family_label: str | None = None
    score: float = 0.0                 # 0-100 compatibilidad de rol
    matched_title: str | None = None
    evidence: list[str] = field(default_factory=list)
    is_technical_heavy: bool = False
    is_excluded: bool = False
    exclusion_reason: str | None = None
    family_scores: dict[str, float] = field(default_factory=dict)


def match_role(
    title: str | None,
    description: str | None = None,
    preferred_families: list[str] | None = None,
    excluded_areas: list[str] | None = None,
) -> RoleMatch:
    norm = normalize_title(title)
    body = searchable(description[:6000] if description else None)
    result = RoleMatch()

    # 1) Exclusiones duras por profesión incompatible
    for term in EXCLUDED_ROLE_TERMS:
        if has_term(norm, term):
            result.is_excluded = True
            result.exclusion_reason = f"rol fuera del perfil ('{term}')"
            return result
    for area in excluded_areas or []:
        if area and has_term(norm, searchable(area)):
            result.is_excluded = True
            result.exclusion_reason = f"área excluida por la candidata ('{area}')"
            return result

    # 2) Rol técnico puro: no se descarta, pero se marca (§3)
    tech_hit = next((t for t in TECHNICAL_HEAVY_TERMS if has_term(norm, t)), None)
    if tech_hit:
        result.is_technical_heavy = True
        result.evidence.append(f"perfil técnico especializado ('{tech_hit}')")

    # 3) Similitud contra las familias objetivo
    title_tokens = _tokens(title or "")
    best: tuple[float, str, str] = (0.0, "", "")
    distinctive_title = title_tokens - GENERIC_TOKENS
    for family, cfg in ROLE_FAMILIES.items():
        family_best = 0.0
        family_title = ""
        for candidate in cfg["titles"]:
            cand_tokens = _tokens(candidate)
            if not cand_tokens:
                continue
            distinctive_cand = cand_tokens - GENERIC_TOKENS
            full_overlap = len(title_tokens & cand_tokens) / len(cand_tokens)
            # Cuánto del título real queda explicado por el rol candidato: castiga
            # los títulos con contenido propio que no matchea ("de mantenimiento").
            coverage = len(title_tokens & cand_tokens) / len(title_tokens or {""})
            if distinctive_cand:
                distinctive_overlap = len(distinctive_cand & distinctive_title) / len(distinctive_cand)
            else:
                distinctive_overlap = full_overlap
            fuzzy = fuzz.token_set_ratio(norm, candidate) / 100.0
            score = 100.0 * (0.55 * distinctive_overlap + 0.20 * full_overlap
                             + 0.15 * coverage + 0.10 * fuzzy)
            # Sin ninguna palabra distintiva en común no hay compatibilidad real
            if distinctive_cand and distinctive_overlap == 0:
                score = min(score, 30.0)
            # Un rol candidato hecho sólo de palabras genéricas ("junior consultant")
            # sólo vale si explica el título completo
            if not distinctive_cand:
                score = min(score, 100.0 * coverage)
            if score > family_best:
                family_best, family_title = score, candidate
        # Señales de contenido en la descripción refuerzan una familia ya plausible
        keyword_hits = [k for k in cfg["keywords"] if has_term(body, k)]
        if keyword_hits:
            cap = 12.0 if family_best >= 45.0 else 6.0
            family_best = min(100.0, family_best + min(cap, 4.0 * len(keyword_hits)))
        if preferred_families and family in preferred_families:
            family_best = min(100.0, family_best + 6.0)
        result.family_scores[family] = round(family_best, 1)
        if family_best > best[0]:
            best = (family_best, family, family_title)

    result.score, result.family, result.matched_title = round(best[0], 1), best[1] or None, best[2] or None
    if result.family:
        result.family_label = ROLE_FAMILIES[result.family]["label"]
        if result.score >= 55:
            result.evidence.append(
                f"compatible con {result.family_label} (similar a '{result.matched_title}')"
            )

    # 4) Un rol de ingeniería pura no es el objetivo del perfil (§3), aunque el
    #    título comparta palabras con una familia de negocios ("Data Engineer").
    if result.is_technical_heavy:
        result.score *= 0.55
        result.evidence.append("posición de ingeniería, poco alineada con el perfil de negocios")

    result.score = round(min(100.0, result.score), 1)
    return result
