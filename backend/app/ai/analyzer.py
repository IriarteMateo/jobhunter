"""Orquestador del análisis de un aviso.

Pipeline de costo creciente (§38):
  1. filtros determinísticos baratos  ->  2. NLP/keywords  ->  3. LLM sólo si vale la pena
Con caché por hash de contenido: un aviso ya analizado no se vuelve a analizar.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.base import AIProvider, LLMAnalysis, ValidationError
from app.ai.prompts import build_user_prompt, deterministic_block, job_block, profile_block
from app.config import settings
from app.models import Recommendation, Seniority
from app.pipeline.experience import experience_bucket, parse_experience
from app.pipeline.languages import analyze_languages
from app.pipeline.location import detect_remote_type, score_location
from app.pipeline.roles import match_role
from app.pipeline.scoring import CandidateContext, ScoreResult, compute_scores
from app.pipeline.seniority import classify_seniority
from app.pipeline.skills import extract_skills
from app.pipeline.text import content_hash

logger = logging.getLogger(__name__)


@dataclass
class AnalysisBundle:
    """Todo lo que el pipeline dedujo de un aviso."""

    scores: ScoreResult
    role: object
    seniority: object
    experience: object
    languages: object
    location: object
    skills: object
    analyzer: str = "heuristic"
    input_hash: str = ""


def analyze_deterministic(
    *,
    title: str,
    description: str | None,
    company_name: str,
    location: str | None,
    remote_hint: str | None,
    publication_date,
    first_seen,
    candidate: CandidateContext,
    seniority_hint: str | None = None,
    company_quality: float = 50.0,
    company_confidence: str,
    is_target_company: bool,
    salary_published: bool = False,
    weights: dict | None = None,
) -> AnalysisBundle:
    exp = parse_experience(title, description)
    sen = classify_seniority(title, description, exp, seniority_hint)
    role = match_role(title, description, candidate.role_families, candidate.excluded_areas)
    lang = analyze_languages(title, description)
    skills = extract_skills(title, description)
    remote_type = detect_remote_type(location, description, remote_hint, title)
    loc = score_location(
        location, description, remote_type,
        preferred_locations=candidate.preferred_locations,
        accepts_remote=candidate.accepts_remote,
        accepts_hybrid=candidate.accepts_hybrid,
        accepts_onsite=candidate.accepts_onsite,
    )
    weights = weights or {}
    scores = compute_scores(
        title=title,
        description=description,
        company_name=company_name,
        publication_date=publication_date,
        first_seen=first_seen,
        role=role, sen=sen, exp=exp, lang=lang, loc=loc, skills=skills,
        candidate=candidate,
        company_quality=company_quality,
        company_confidence=company_confidence,
        is_target_company=is_target_company,
        salary_published=salary_published,
        fit_weights=weights.get("fit_weights"),
        final_weights=weights.get("final_weights"),
        boosts_cfg=weights.get("boosts"),
        penalties_cfg=weights.get("penalties"),
    )
    return AnalysisBundle(
        scores=scores, role=role, seniority=sen, experience=exp,
        languages=lang, location=loc, skills=skills,
        input_hash=content_hash(title, company_name, description, location),
    )


def should_use_llm(bundle: AnalysisBundle, provider: AIProvider) -> bool:
    """Filtro de costo: sólo se gasta LLM en avisos potencialmente relevantes."""
    if not provider.is_llm:
        return False
    if not bundle.scores.eligible and bundle.scores.hard_blockers:
        # Un bloqueo duro y barato no necesita confirmación de un modelo caro,
        # salvo que la razón sea ambigua (seniority incierto).
        if bundle.seniority.confidence >= 0.8:
            return False
    return bundle.scores.final_score >= settings.ai_prefilter_threshold


async def refine_with_llm(
    bundle: AnalysisBundle, provider: AIProvider, *, profile, job
) -> AnalysisBundle:
    """Refina el análisis con el LLM y valida la respuesta (§52, §53)."""
    prompt = build_user_prompt(
        profile_block=profile_block(profile),
        job_block=job_block(job),
        deterministic_block=deterministic_block(
            bundle.scores, bundle.role, bundle.seniority, bundle.experience,
            bundle.languages, bundle.location,
            bundle.scores.company_quality_score, "MEDIUM",
        ),
    )
    try:
        llm = await provider.analyze(prompt)
    except (ValidationError, Exception) as exc:  # noqa: BLE001
        logger.warning("LLM falló para '%s': %s. Se mantiene el análisis determinístico.",
                       job.job_title, exc)
        return bundle
    return merge_llm(bundle, llm, provider.name)


def merge_llm(bundle: AnalysisBundle, llm: LLMAnalysis, provider_name: str) -> AnalysisBundle:
    """Combina reglas + LLM.

    Los números se promedian (el determinístico ancla, el LLM corrige matices).
    La prosa la escribe el LLM. Un bloqueo detectado por reglas sólo se levanta
    si el LLM lo contradice explícitamente con eligible=True y sin blockers.
    """
    s = bundle.scores
    if llm.fit_score is not None:
        s.fit_score = round(0.5 * s.fit_score + 0.5 * llm.fit_score, 1)
    if llm.career_value_score is not None:
        s.career_value_score = round(0.5 * s.career_value_score + 0.5 * llm.career_value_score, 1)
    if llm.german_advantage_score is not None:
        s.german_advantage_score = round(
            max(s.german_advantage_score, 0.4 * s.german_advantage_score + 0.6 * llm.german_advantage_score), 1
        )
    if llm.location_score is not None:
        s.location_score = round(0.6 * s.location_score + 0.4 * llm.location_score, 1)

    if llm.seniority and llm.seniority != "Unknown":
        try:
            bundle.seniority.level = Seniority(llm.seniority)
        except ValueError:
            pass

    if llm.eligible is not None:
        if llm.eligible is False and s.eligible:
            s.eligible = False
            s.not_eligible_reason = (llm.hard_blockers or ["el análisis del modelo lo descarta"])[0]
        elif llm.eligible is True and not s.eligible and not llm.hard_blockers:
            s.eligible = True
            s.not_eligible_reason = None

    if llm.match_reasons:
        s.match_reasons = llm.match_reasons[:10]
    if llm.gaps:
        s.gaps = llm.gaps[:6]
    if llm.hard_blockers:
        s.hard_blockers = llm.hard_blockers[:5]
    if llm.summary:
        s.summary = llm.summary
    if llm.why_apply:
        s.why_apply = llm.why_apply
    if llm.confidence:
        s.confidence = round((s.confidence + llm.confidence) / 2, 2)

    # Recalcular el score final con los sub-scores ya refinados
    base = (0.60 * s.fit_score + 0.20 * s.company_quality_score
            + 0.15 * s.career_value_score + 0.05 * s.recency_score)
    final = base + sum(b["points"] for b in s.boosts) - sum(p["points"] for p in s.penalties)
    s.final_score = round(max(0.0, min(100.0, final)), 1)

    if not s.eligible:
        s.recommendation = Recommendation.NOT_ELIGIBLE.value
        s.final_score = min(s.final_score, 45.0)
    elif llm.recommendation:
        s.recommendation = llm.recommendation
    else:
        from app.pipeline.scoring import RECOMMENDATION_BANDS

        for threshold, rec in RECOMMENDATION_BANDS:
            if s.final_score >= threshold:
                s.recommendation = rec.value
                break

    bundle.analyzer = provider_name
    return bundle


def experience_label(bundle: AnalysisBundle) -> str:
    return experience_bucket(bundle.experience)
