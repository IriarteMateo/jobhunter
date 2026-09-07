"""Personalización a partir del feedback explícito (§46).

Transparente por diseño: `explain()` devuelve exactamente qué ajustes se están
aplicando, para poder mostrarlos en la UI.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FeedbackEvent
from app.services.profile import get_preference, get_user

def _plural(count: int) -> str:
    return "aviso" if count == 1 else "avisos"


NEGATIVE_ACTIONS = {"not_interested", "dismissed"}
POSITIVE_ACTIONS = {"interested", "applied"}


def record(db: Session, *, job_id: int | None, action: str, reason: str | None = None,
           features: dict | None = None) -> FeedbackEvent:
    user = get_user(db)
    event = FeedbackEvent(
        user_id=user.id, job_id=job_id, action=action, reason=reason, features=features or {}
    )
    db.add(event)
    db.flush()
    return event


def _tallies(db: Session) -> tuple[Counter, Counter]:
    user = get_user(db)
    negative: Counter = Counter()
    positive: Counter = Counter()
    for event in db.scalars(select(FeedbackEvent).where(FeedbackEvent.user_id == user.id)):
        family = (event.features or {}).get("role_family")
        if not family:
            continue
        if event.action in NEGATIVE_ACTIONS:
            negative[family] += 1
        elif event.action in POSITIVE_ACTIONS:
            positive[family] += 1
    return negative, positive


def adjustments(db: Session) -> dict[str, float]:
    """Ajuste en puntos por familia de rol. Negativo = menos recomendaciones."""
    cfg = get_preference(db, "personalization")
    if not cfg.get("enabled", True):
        return {}
    per_event = float(cfg.get("dismiss_penalty_per_event", 2.0))
    cap = float(cfg.get("max_penalty", 10.0))
    negative, positive = _tallies(db)
    out: dict[str, float] = {}
    for family in set(negative) | set(positive):
        delta = positive[family] * per_event - negative[family] * per_event
        if abs(delta) >= per_event:
            out[family] = round(max(-cap, min(cap, delta)), 1)
    return out


def explain(db: Session) -> list[dict]:
    """Explicación legible de la personalización activa (§46: nunca opaca)."""
    negative, positive = _tallies(db)
    adj = adjustments(db)
    from app.data.taxonomy import ROLE_FAMILIES

    out = []
    for family, points in sorted(adj.items(), key=lambda kv: kv[1]):
        label = ROLE_FAMILIES.get(family, {}).get("label", family)
        out.append({
            "family": family,
            "label": label,
            "points": points,
            "descartados": negative[family],
            "positivos": positive[family],
            "texto": (
                f"Descartaste {negative[family]} {_plural(negative[family])} de {label}: "
                f"se bajan {abs(points):g} puntos."
                if points < 0 else
                f"Guardaste o aplicaste a {positive[family]} {_plural(positive[family])} "
                f"de {label}: se suben {points:g} puntos."
            ),
        })
    return out
