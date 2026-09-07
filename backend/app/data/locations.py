"""Geografía para el location_score (§5).

Prioridad desde San Isidro, Zona Norte, Provincia de Buenos Aires.
"""
from __future__ import annotations

# tier -> (score, [aliases en minúscula])
LOCATION_TIERS: list[tuple[str, float, list[str]]] = [
    (
        "zona_norte",
        100.0,
        [
            "san isidro", "martinez", "martínez", "vicente lopez", "vicente lópez",
            "olivos", "munro", "acassuso", "beccar", "boulogne", "florida oeste",
            "la lucila", "carapachay", "villa adelina", "san fernando", "tigre",
            "nordelta", "zona norte", "gba norte", "san isidro, buenos aires",
        ],
    ),
    (
        "caba_norte",
        88.0,
        [
            "nuñez", "núñez", "belgrano", "colegiales", "palermo", "retiro",
            "microcentro", "puerto madero", "recoleta", "villa urquiza",
            "catalinas", "barrio norte",
        ],
    ),
    (
        "caba",
        78.0,
        [
            "caba", "ciudad autónoma de buenos aires", "ciudad autonoma de buenos aires",
            "capital federal", "buenos aires city", "ciudad de buenos aires",
        ],
    ),
    (
        "amba",
        66.0,
        [
            "buenos aires", "gran buenos aires", "gba", "provincia de buenos aires",
            "avellaneda", "quilmes", "san martín", "san martin", "tres de febrero",
            "morón", "moron", "ituzaingó", "ituzaingo",
        ],
    ),
    (
        "argentina",
        58.0,
        ["argentina", "arg", "ar", "córdoba", "cordoba", "rosario", "mendoza", "santa fe"],
    ),
]

REMOTE_TERMS = [
    "remote", "remoto", "100% remote", "fully remote", "work from home",
    "trabajo remoto", "teletrabajo", "home office", "anywhere",
]
HYBRID_TERMS = [
    "hybrid", "hibrido", "hibrida", "modalidad hibrida", "semi presencial",
    "semipresencial", "flexible work", "hybrides", "teilweise remote",
]
ONSITE_TERMS = ["on-site", "onsite", "presencial", "in office", "in-office", "oficina"]

REMOTE_LATAM_TERMS = [
    "remote latam", "latam", "latin america", "américa latina", "america latina",
    "south america", "sudamérica", "sudamerica", "remote - latam", "remote (latam)",
    "remote americas", "remote - argentina", "remote argentina",
]

# Países/regiones donde una oferta remota probablemente NO acepte argentinos
REMOTE_EXCLUSIVE_MARKERS = [
    "must be located in the united states", "us only", "usa only", "eu only",
    "must reside in the uk", "authorized to work in the united states",
    "us citizens only", "canada only", "india only", "philippines only",
    "must be based in europe", "emea only", "brazil only", "mexico only",
]

DACH_MARKERS = ["germany", "deutschland", "austria", "österreich", "switzerland", "schweiz", "dach"]


def normalize_location(raw: str | None) -> str:
    return (raw or "").strip().lower()
