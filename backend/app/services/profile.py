"""Perfil de la candidata: contexto para el scorer y preferencias (§33, §46)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CandidatePreference, CandidateProfile, User
from app.pipeline.scoring import (
    DEFAULT_BOOSTS,
    DEFAULT_FINAL_WEIGHTS,
    DEFAULT_FIT_WEIGHTS,
    DEFAULT_PENALTIES,
    CandidateContext,
)

DEFAULT_USER_EMAIL = "candidata@jobhunter.local"

PREF_KEYS = {
    "fit_weights": DEFAULT_FIT_WEIGHTS,
    "final_weights": DEFAULT_FINAL_WEIGHTS,
    "boosts": DEFAULT_BOOSTS,
    "penalties": DEFAULT_PENALTIES,
    "display": {"min_display_score": 70.0, "hide_dismissed": True, "hide_not_eligible": True},
    "experience": {"policy": "strict"},
    "personalization": {"enabled": True, "dismiss_penalty_per_event": 2.0, "max_penalty": 10.0},
}


def get_user(db: Session) -> User:
    user = db.scalars(select(User).order_by(User.id)).first()
    if user is None:
        user = User(email=DEFAULT_USER_EMAIL, display_name="Candidata")
        db.add(user)
        db.flush()
    return user


def get_profile(db: Session) -> CandidateProfile:
    user = get_user(db)
    profile = db.scalars(
        select(CandidateProfile).where(CandidateProfile.user_id == user.id)
    ).first()
    if profile is None:
        profile = CandidateProfile(user_id=user.id)
        db.add(profile)
        db.flush()
    return profile


def get_preference(db: Session, key: str) -> dict:
    user = get_user(db)
    row = db.scalars(
        select(CandidatePreference).where(
            CandidatePreference.user_id == user.id, CandidatePreference.key == key
        )
    ).first()
    default = PREF_KEYS.get(key, {})
    if row is None:
        return dict(default)
    return {**default, **(row.value or {})}


def set_preference(db: Session, key: str, value: dict) -> dict:
    user = get_user(db)
    row = db.scalars(
        select(CandidatePreference).where(
            CandidatePreference.user_id == user.id, CandidatePreference.key == key
        )
    ).first()
    if row is None:
        row = CandidatePreference(user_id=user.id, key=key, value={})
        db.add(row)
    row.value = {**(row.value or {}), **value}
    db.flush()
    return {**PREF_KEYS.get(key, {}), **row.value}


def all_weights(db: Session) -> dict:
    return {
        "fit_weights": get_preference(db, "fit_weights"),
        "final_weights": get_preference(db, "final_weights"),
        "boosts": get_preference(db, "boosts"),
        "penalties": get_preference(db, "penalties"),
    }


def build_context(profile: CandidateProfile, policy: str | None = None) -> CandidateContext:
    languages = {
        (l.get("code") or "").lower(): l.get("level", "")
        for l in (profile.languages or [])
        if l.get("code")
    }
    return CandidateContext(
        years_experience=profile.years_experience or 0.0,
        degree_field=profile.degree_field or "",
        university=profile.university or "",
        language_codes=languages,
        skills=[s.lower() for s in (profile.skills or [])],
        role_families=list(profile.role_families or []),
        excluded_areas=list(profile.excluded_areas or []),
        preferred_locations=list(profile.preferred_locations or []),
        accepts_remote=profile.accepts_remote,
        accepts_hybrid=profile.accepts_hybrid,
        accepts_onsite=profile.accepts_onsite,
        blocked_companies=list(profile.blocked_companies or []),
        favorite_companies=list(profile.favorite_companies or []),
        is_graduated=bool(profile.graduation_year),
        experience_policy=policy or "strict",
    )
