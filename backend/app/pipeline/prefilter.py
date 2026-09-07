"""Filtro determinístico previo a la ingesta (§38, §57).

Los boards públicos devuelven avisos de todo el mundo. Guardar y analizar un
puesto presencial en Gurugram no aporta nada a una candidata en San Isidro:
se descarta antes de tocar la base y antes de gastar un token de LLM.

Es un filtro barato y explicable: geografía + seniority evidente en el título.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.data.locations import (
    LOCATION_TIERS,
    REMOTE_EXCLUSIVE_MARKERS,
    REMOTE_LATAM_TERMS,
)
from app.data.taxonomy import EXCLUDED_ROLE_TERMS, SENIOR_FALSE_FRIENDS
from app.models import RemoteType
from app.pipeline.text import contains_any, found_terms, has_term, searchable

AR_ALIASES = [alias for _, _, aliases in LOCATION_TIERS for alias in aliases]

GLOBAL_REMOTE_TERMS = [
    "worldwide", "anywhere", "global", "remote - global", "americas",
    "remote (global)", "any location", "fully remote",
]

# Tokens que sólo indican modalidad. Si al sacarlos no queda ningún país,
# el aviso es "Remote" a secas: no declara restricción geográfica.
_MODALITY_ONLY = {
    "remote", "remoto", "remota", "fully", "100", "work", "from", "home",
    "office", "telecommute", "teletrabajo", "anywhere", "worldwide", "global",
    "hybrid", "hibrido", "onsite", "flexible", "distributed", "virtual", "n/a",
}


def _declares_a_place(location: str) -> bool:
    tokens = [t for t in re.split(r"[^a-z0-9]+", location) if t]
    return any(t not in _MODALITY_ONLY for t in tokens)

# Títulos que nunca corresponden a un primer empleo
HARD_SENIOR_TITLE_TERMS = [
    "senior", "sr.", "sr", "staff", "principal", "lead", "head of", "director",
    "vp", "vice president", "chief", "gerente", "jefe", "manager ii", "manager iii",
    "expert", "architect", "especialista senior", "supervisor",
]


# Avisos que no son una búsqueda concreta
TALENT_POOL_TERMS = [
    "talent network", "talent pool", "talent community", "banco de talentos",
    "banco de talento", "candidatura espontanea", "candidatura espontánea",
    "spontaneous application", "general application", "future opportunities",
    "expression of interest", "postulacion espontanea", "postulación espontánea",
    "join our team", "initiativbewerbung", "talentbank", "no vacancy",
    "feria", "job fair", "career fair", "expo empleo",
    "open day", "jornada de reclutamiento",
]


@dataclass
class PrefilterDecision:
    keep: bool
    reason: str = ""


def geography_ok(location: str | None, description: str | None,
                 remote_type: RemoteType) -> tuple[bool, str]:
    """La ubicación declarada manda sobre las señales del cuerpo del aviso.

    Un puesto listado en "São Paulo" no pasa a ser elegible porque la
    descripción mencione "LATAM": la sede sigue estando en Brasil.
    """
    loc = searchable(location)
    body = searchable((description or "")[:3000])

    if contains_any(loc, AR_ALIASES):
        return True, "ubicación en Argentina"

    # Lugar concreto declarado y no es Argentina -> fuera, sin importar la modalidad.
    if loc and _declares_a_place(loc) and not contains_any(loc, REMOTE_LATAM_TERMS + GLOBAL_REMOTE_TERMS):
        return False, f"ubicación fuera del área objetivo ({location})"

    if remote_type == RemoteType.REMOTE:
        if contains_any(loc, REMOTE_EXCLUSIVE_MARKERS) or contains_any(body, REMOTE_EXCLUSIVE_MARKERS):
            return False, "remoto restringido a otra región"
        if contains_any(loc, REMOTE_LATAM_TERMS) or contains_any(body, REMOTE_LATAM_TERMS):
            return True, "remoto abierto a LATAM"
        if contains_any(loc, GLOBAL_REMOTE_TERMS) or not loc or not _declares_a_place(loc):
            return True, "remoto sin restricción declarada"
        return False, "remoto anclado a otro país"

    if not loc:
        return False, "sin ubicación declarada y sin modalidad remota"
    return False, f"ubicación fuera del área objetivo ({location})"


def seniority_ok(title: str) -> tuple[bool, str]:
    norm = searchable(title)
    if contains_any(norm, SENIOR_FALSE_FRIENDS):
        return True, ""
    hits = found_terms(norm, HARD_SENIOR_TITLE_TERMS)
    if hits:
        return False, f"título de nivel senior ('{hits[0]}')"
    return True, ""


def role_ok(title: str) -> tuple[bool, str]:
    norm = searchable(title)
    if contains_any(norm, TALENT_POOL_TERMS):
        return False, "no es una búsqueda concreta (banco de talentos)"
    for term in EXCLUDED_ROLE_TERMS:
        if has_term(norm, term):
            return False, f"profesión incompatible con el perfil ('{term}')"
    return True, ""


def should_ingest(*, title: str, location: str | None, description: str | None,
                  remote_type: str) -> PrefilterDecision:
    """Gate barato antes de persistir un aviso."""
    try:
        rt = RemoteType(remote_type)
    except ValueError:
        rt = RemoteType.UNKNOWN

    ok, reason = geography_ok(location, description, rt)
    if not ok:
        return PrefilterDecision(False, reason)
    ok, reason = seniority_ok(title)
    if not ok:
        return PrefilterDecision(False, reason)
    ok, reason = role_ok(title)
    if not ok:
        return PrefilterDecision(False, reason)
    return PrefilterDecision(True, "pasa el filtro geográfico y de nivel")
