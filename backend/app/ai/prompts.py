"""Prompts del motor de matching.

Regla no negociable (§53): el modelo no puede inventar. Cada afirmación debe
apoyarse en el texto del aviso o en el análisis determinístico que se le pasa.
Lo que no está en el aviso es "Unknown".
"""
from __future__ import annotations

SYSTEM_PROMPT = """Sos un analista experto en reclutamiento para perfiles universitarios junior en Argentina.
Tu tarea: evaluar qué tan recomendable es que UNA candidata específica aplique a UN aviso específico.

REGLAS ESTRICTAS
1. No inventes NADA. Requisitos, salario, beneficios, modalidad, ubicación, idiomas,
   experiencia e información de la empresa deben salir del texto del aviso o del
   análisis determinístico que recibís. Si un dato no está, escribí "Unknown".
2. No conviertas una preferencia ("preferred", "deseable", "a plus") en un requisito excluyente.
3. Un perfil junior NO necesita cumplir el 100% del aviso. Distinguí MUST HAVE de NICE TO HAVE.
   Un faltante NICE TO HAVE casi no penaliza.
4. Analizá el aviso completo, no el título. "Business Analyst" con 5 años requeridos NO es junior.
5. No descartes por falta de una keyword exacta: evaluá compatibilidad semántica real.
6. Tampoco recomiendes un puesto sólo porque contiene palabras del perfil ("product", "business",
   "digital", "analytics"). Leé el contexto.
7. Respondé EXCLUSIVAMENTE con un objeto JSON válido, sin texto adicional ni markdown.

FORMATO DE SALIDA (todos los campos obligatorios):
{
  "fit_score": 0-100,
  "company_quality_score": 0-100,
  "career_value_score": 0-100,
  "german_advantage_score": 0-100,
  "location_score": 0-100,
  "seniority": "Internship|Trainee|Graduate|Entry Level|Junior|Junior+|Semi Senior|Senior|Manager|Director|Unknown",
  "experience_required": "texto corto, ej '0-1 year' o 'Unknown'",
  "eligible": true|false,
  "recommendation": "APPLY_NOW|STRONG|WORTH_IT|OPTIONAL|SKIP|NOT_ELIGIBLE",
  "match_reasons": ["razón concreta anclada al aviso", ...],
  "gaps": ["faltante, aclarando si es requisito o deseable", ...],
  "hard_blockers": ["motivo real de descarte, vacío si no hay", ...],
  "summary": "2 frases describiendo el puesto",
  "why_apply": "1-2 frases con la recomendación accionable",
  "confidence": 0.0-1.0
}
Escribí match_reasons, gaps, summary y why_apply en español rioplatense."""


def build_user_prompt(*, profile_block: str, job_block: str, deterministic_block: str) -> str:
    return f"""## PERFIL DE LA CANDIDATA
{profile_block}

## AVISO A EVALUAR
{job_block}

## ANÁLISIS DETERMINÍSTICO PREVIO (calculado por reglas sobre el texto del aviso)
{deterministic_block}

Evaluá el aviso siguiendo las reglas del sistema. Si el análisis determinístico se equivocó
—por ejemplo clasificó mal el seniority o interpretó una preferencia como requisito—
corregilo y explicá por qué en match_reasons o gaps. Devolvé sólo el JSON."""


def profile_block(profile) -> str:
    langs = ", ".join(
        f"{l.get('name', l.get('code'))} ({l.get('level', 'sin nivel')})"
        for l in (profile.languages or [])
    ) or "sin datos"
    skills = ", ".join(profile.skills or []) or "sin datos"
    areas = ", ".join(profile.target_roles or []) or "sin datos"
    excluded = ", ".join(profile.excluded_areas or []) or "ninguna"
    modalities = [m for m, ok in (("remoto", profile.accepts_remote),
                                  ("híbrido", profile.accepts_hybrid),
                                  ("presencial", profile.accepts_onsite)) if ok]
    return f"""- Formación: {profile.degree} en {profile.degree_field or profile.degree} — {profile.university}
- Graduación: {profile.graduation_year or 'sin dato'}
- Experiencia laboral formal: {'sí' if profile.has_formal_experience else 'NO tiene experiencia laboral formal'} ({profile.years_experience:g} años)
- Idiomas: {langs}
- Skills declaradas: {skills}
- Áreas de interés: {areas}
- Áreas excluidas: {excluded}
- Ubicación: {profile.city}, {profile.region}, {profile.country}
- Modalidades aceptadas: {', '.join(modalities) or 'sin datos'}
- Nota importante: la falta de experiencia NO significa falta de capacidad. Su combinación de
  universidad, carrera e idiomas es una ventaja competitiva para posiciones de primer empleo."""


def job_block(job, max_description: int = 6000) -> str:
    description = (job.description or "")[:max_description]
    return f"""- Título: {job.job_title}
- Empresa: {job.company}
- Ubicación declarada: {job.location or 'Unknown'}
- Modalidad detectada: {job.remote_type}
- Tipo de empleo: {job.employment_type or 'Unknown'}
- Fecha de publicación: {job.publication_date.date() if job.publication_date else 'Unknown'}
- Fuente: {job.source}
- Salario publicado: {'sí' if job.salary_is_published else 'no publicado'}

DESCRIPCIÓN (texto literal del aviso):
\"\"\"
{description}
\"\"\""""


def deterministic_block(scores, role, sen, exp, lang, loc, company_quality, company_confidence) -> str:
    from app.pipeline.experience import experience_bucket

    return f"""- Familia de rol detectada: {role.family_label or 'ninguna'} (compatibilidad {role.score}/100)
- Seniority detectado: {sen.level.value} (confianza {sen.confidence})
- Experiencia solicitada: {experience_bucket(exp)} — {'REQUISITO DURO' if exp.is_hard else 'preferencia / no excluyente'}
- Acepta sin experiencia: {exp.accepts_no_experience}
- Menciona estudiantes/recién graduados: {exp.mentions_students}
- Exige estudiante en curso: {exp.enrolled_students_only}
- Alemán: nivel {lang.german_level} (score {lang.german_score})
- Ubicación: score {loc.score}, categoría {loc.tier}, modalidad {loc.remote_type.value}
- Calidad de empresa: {company_quality} (confianza {company_confidence})
- Fit determinístico: {scores.fit_score} | career value: {scores.career_value_score} | final: {scores.final_score}
- Bloqueos detectados por reglas: {scores.hard_blockers or 'ninguno'}"""
