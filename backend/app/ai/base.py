"""Contrato del proveedor de IA (desacoplado: Anthropic / OpenAI / heurístico)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

ALLOWED_RECOMMENDATIONS = {"APPLY_NOW", "STRONG", "WORTH_IT", "OPTIONAL", "SKIP", "NOT_ELIGIBLE"}
ALLOWED_SENIORITY = {
    "Internship", "Trainee", "Graduate", "Entry Level", "Junior", "Junior+",
    "Semi Senior", "Senior", "Manager", "Director", "Unknown",
}


@dataclass
class LLMAnalysis:
    """Respuesta validada del LLM (§52)."""

    fit_score: float | None = None
    company_quality_score: float | None = None
    career_value_score: float | None = None
    german_advantage_score: float | None = None
    location_score: float | None = None
    seniority: str | None = None
    experience_required: str | None = None
    eligible: bool | None = None
    recommendation: str | None = None
    match_reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    hard_blockers: list[str] = field(default_factory=list)
    summary: str = ""
    why_apply: str = ""
    confidence: float = 0.5
    raw: dict[str, Any] = field(default_factory=dict)


class ValidationError(ValueError):
    pass


def _num(value, lo=0.0, hi=100.0, field_name="campo") -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} no es numérico: {value!r}") from exc
    return max(lo, min(hi, num))


def _str_list(value, limit: int = 10) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValidationError(f"se esperaba lista, llegó {type(value).__name__}")
    out = [str(v).strip() for v in value if str(v).strip()]
    return out[:limit]


def validate_llm_payload(payload: dict) -> LLMAnalysis:
    """Valida SIEMPRE la respuesta del modelo antes de usarla (§52)."""
    if not isinstance(payload, dict):
        raise ValidationError("la respuesta no es un objeto JSON")

    seniority = payload.get("seniority")
    if seniority is not None:
        seniority = str(seniority).strip()
        if seniority not in ALLOWED_SENIORITY:
            seniority = None

    recommendation = payload.get("recommendation")
    if recommendation is not None:
        recommendation = str(recommendation).strip().upper().replace(" ", "_")
        if recommendation not in ALLOWED_RECOMMENDATIONS:
            recommendation = None

    eligible = payload.get("eligible")
    if eligible is not None and not isinstance(eligible, bool):
        eligible = str(eligible).strip().lower() in ("true", "1", "yes", "sí", "si")

    return LLMAnalysis(
        fit_score=_num(payload.get("fit_score"), field_name="fit_score"),
        company_quality_score=_num(payload.get("company_quality_score"), field_name="company_quality_score"),
        career_value_score=_num(payload.get("career_value_score"), field_name="career_value_score"),
        german_advantage_score=_num(payload.get("german_advantage_score"), field_name="german_advantage_score"),
        location_score=_num(payload.get("location_score"), field_name="location_score"),
        seniority=seniority,
        experience_required=(str(payload["experience_required"]).strip()
                             if payload.get("experience_required") else None),
        eligible=eligible,
        recommendation=recommendation,
        match_reasons=_str_list(payload.get("match_reasons")),
        gaps=_str_list(payload.get("gaps")),
        hard_blockers=_str_list(payload.get("hard_blockers"), 5),
        summary=str(payload.get("summary") or "").strip()[:800],
        why_apply=str(payload.get("why_apply") or "").strip()[:800],
        confidence=_num(payload.get("confidence"), 0.0, 1.0, "confidence") or 0.5,
        raw=payload,
    )


class AIProvider(ABC):
    name = "base"
    is_llm = False

    @abstractmethod
    async def analyze(self, prompt: str) -> LLMAnalysis:
        """Analiza un aviso y devuelve la estructura validada."""

    async def close(self) -> None:
        return None
