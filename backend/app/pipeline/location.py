"""location_score y detección de modalidad (§5)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.data.locations import (
    HYBRID_TERMS,
    LOCATION_TIERS,
    ONSITE_TERMS,
    REMOTE_EXCLUSIVE_MARKERS,
    REMOTE_LATAM_TERMS,
    REMOTE_TERMS,
)
from app.models import RemoteType
from app.pipeline.text import searchable


@dataclass
class LocationAnalysis:
    score: float = 0.0
    tier: str = "unknown"
    remote_type: RemoteType = RemoteType.UNKNOWN
    city: str | None = None
    country: str | None = None
    accepts_argentina: bool | None = None
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def detect_remote_type(location: str | None, description: str | None, hint: str | None,
                       title: str | None = None) -> RemoteType:
    """La modalidad suele venir en el título ("Analyst (Hybrid)"), no sólo en la
    ubicación: se mira el título primero."""
    title_l = searchable(title)
    if any(t in title_l for t in HYBRID_TERMS):
        return RemoteType.HYBRID
    if any(t in title_l for t in REMOTE_TERMS):
        return RemoteType.REMOTE
    if any(t in title_l for t in ONSITE_TERMS):
        return RemoteType.ONSITE
    text = searchable(location, hint, description[:2500] if description else None)
    hint_l = searchable(hint)
    if any(t in hint_l for t in ("remote", "remoto")):
        return RemoteType.REMOTE
    if any(t in hint_l for t in ("hybrid", "hibrido")):
        return RemoteType.HYBRID
    if any(t in hint_l for t in ("onsite", "on_site", "on-site", "presencial")):
        return RemoteType.ONSITE
    loc = searchable(location)
    if any(t in loc for t in HYBRID_TERMS):
        return RemoteType.HYBRID
    if any(t in loc for t in REMOTE_TERMS):
        return RemoteType.REMOTE
    if any(t in text for t in HYBRID_TERMS):
        return RemoteType.HYBRID
    if any(t in text for t in REMOTE_TERMS):
        return RemoteType.REMOTE
    if any(t in text for t in ONSITE_TERMS):
        return RemoteType.ONSITE
    return RemoteType.UNKNOWN


def score_location(
    location: str | None,
    description: str | None,
    remote_type: RemoteType,
    preferred_locations: list[str] | None = None,
    accepts_remote: bool = True,
    accepts_hybrid: bool = True,
    accepts_onsite: bool = True,
) -> LocationAnalysis:
    loc = searchable(location)
    body = searchable(description[:4000] if description else None)
    result = LocationAnalysis(remote_type=remote_type)

    # Preferencias explícitas de la candidata primero
    for pref in preferred_locations or []:
        if pref and searchable(pref) in loc:
            result.score = 100.0
            result.tier = "preferida"
            result.city = pref
            result.reasons.append(f"ubicación preferida: {pref}")
            return result

    for tier, score, aliases in LOCATION_TIERS:
        hit = next((a for a in aliases if a in loc), None)
        if hit:
            result.score = score
            result.tier = tier
            result.city = hit
            result.country = "Argentina"
            result.reasons.append(f"ubicación en {hit.title()}")
            break

    if result.tier == "unknown":
        if remote_type == RemoteType.REMOTE:
            if any(t in loc or t in body for t in REMOTE_LATAM_TERMS):
                result.score = 82.0
                result.tier = "remote_latam"
                result.accepts_argentina = True
                result.reasons.append("remoto abierto a LATAM/Argentina")
            elif any(m in body or m in loc for m in REMOTE_EXCLUSIVE_MARKERS):
                result.score = 12.0
                result.tier = "remote_excluye_ar"
                result.accepts_argentina = False
                result.blockers.append("remoto restringido a otra región")
            elif "worldwide" in loc or "anywhere" in loc or "global" in loc:
                result.score = 78.0
                result.tier = "remote_global"
                result.accepts_argentina = True
                result.reasons.append("remoto global")
            else:
                result.score = 45.0
                result.tier = "remote_indefinido"
                result.reasons.append("remoto sin región especificada")
        else:
            result.score = 25.0
            result.tier = "fuera_de_area"
            result.reasons.append("ubicación fuera del área objetivo")
    else:
        # Ajustes por modalidad sobre una ubicación argentina
        if remote_type == RemoteType.REMOTE:
            result.score = min(100.0, result.score + 8)
            result.reasons.append("modalidad remota")
        elif remote_type == RemoteType.HYBRID:
            result.score = min(100.0, result.score + 4)
            result.reasons.append("modalidad híbrida")
        result.accepts_argentina = True

    # Penalización si la modalidad no está aceptada por la candidata
    if remote_type == RemoteType.REMOTE and not accepts_remote:
        result.score *= 0.5
        result.blockers.append("no acepta trabajo remoto")
    if remote_type == RemoteType.HYBRID and not accepts_hybrid:
        result.score *= 0.5
        result.blockers.append("no acepta modalidad híbrida")
    if remote_type == RemoteType.ONSITE and not accepts_onsite:
        result.score *= 0.4
        result.blockers.append("no acepta trabajo presencial")

    result.score = round(max(0.0, min(100.0, result.score)), 1)
    return result
