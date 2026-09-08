"""Tests del pipeline de análisis sobre avisos reales anonimizados."""
from __future__ import annotations

import pytest

from app.models import RemoteType, Seniority
from app.pipeline.dedupe import build_fingerprint, location_bucket, source_priority
from app.pipeline.experience import experience_bucket, parse_experience
from app.pipeline.languages import analyze_languages
from app.pipeline.location import detect_remote_type, score_location
from app.pipeline.prefilter import should_ingest
from app.pipeline.roles import match_role
from app.pipeline.scoring import compute_scores
from app.pipeline.seniority import classify_seniority
from app.pipeline.skills import extract_skills
from app.pipeline.text import normalize_company, normalize_title


def analyze(job: dict, candidate):
    # Cada fixture puede fijar la política de experiencia bajo la que se evalúa
    candidate.experience_policy = job.get("policy", candidate.experience_policy)
    exp = parse_experience(job["title"], job["description"])
    sen = classify_seniority(job["title"], job["description"], exp)
    role = match_role(job["title"], job["description"], candidate.role_families)
    lang = analyze_languages(job["title"], job["description"])
    skills = extract_skills(job["title"], job["description"])
    remote = detect_remote_type(job["location"], job["description"], job.get("remote_hint"))
    loc = score_location(job["location"], job["description"], remote,
                         preferred_locations=candidate.preferred_locations)
    scores = compute_scores(
        title=job["title"], description=job["description"], company_name=job["company"],
        publication_date=None, first_seen=None, role=role, sen=sen, exp=exp, lang=lang,
        loc=loc, skills=skills, candidate=candidate, company_quality=60.0,
        company_confidence="MEDIUM", is_target_company=False,
    )
    return scores, sen, exp, lang, loc, role


# ------------------------------ normalización ------------------------------ #
@pytest.mark.parametrize("raw,expected", [
    ("EBANX S.A.", "ebanx"),
    ("Mercado Libre Argentina S.R.L.", "mercado libre"),
    ("Bosch Group GmbH", "bosch"),
    ("  Nubank  ", "nubank"),
])
def test_normalize_company(raw, expected):
    assert normalize_company(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Junior Business Analyst (Remote)", "junior business analyst"),
    ("Sr. Product Manager", "senior product manager"),
    ("Analista Jr. de Datos", "analista junior de datos"),
])
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


# ------------------------------ deduplicación ------------------------------ #
def test_fingerprint_matches_across_sources(sample_jobs):
    original = next(j for j in sample_jobs if j["id"] == "graduate_program_target")
    dupe = next(j for j in sample_jobs if j["id"] == "duplicate_of_graduate")
    assert build_fingerprint(original["company"], original["title"], original["location"]) == \
           build_fingerprint(dupe["company"], dupe["title"], dupe["location"])


def test_location_bucket_groups_buenos_aires():
    assert location_bucket("CABA, Argentina") == location_bucket("Buenos Aires, Argentina")
    assert location_bucket("Remote - LATAM") == "remote"


def test_official_source_wins_over_aggregator():
    assert source_priority("greenhouse") > source_priority("linkedin")
    assert source_priority("company_careers") > source_priority("remotive")


# ------------------------------- experiencia ------------------------------- #
def test_hard_requirement_vs_preference():
    hard = parse_experience("Business Analyst", "Minimum 5 years of experience required.")
    soft = parse_experience("Junior Analyst", "2 years of experience preferred.")
    assert hard.is_hard is True and hard.min_years == 5
    assert soft.is_hard is False and soft.min_years == 2


def test_no_experience_required_detected():
    req = parse_experience("Trainee", "No experience required. Recent graduates welcome.")
    assert req.accepts_no_experience is True
    assert req.mentions_students is True
    assert experience_bucket(req) == "Sin experiencia"


def test_years_of_study_are_not_experience():
    req = parse_experience("Pasantía", "Estudiante regular con al menos 2 años de cursada restantes.")
    assert req.min_years is None
    assert req.enrolled_students_only is True


def test_spanish_hard_requirement_in_next_sentence():
    req = parse_experience("Analista", "Experiencia mínima de 3 años en el rubro. Excluyente.")
    assert req.min_years == 3 and req.is_hard is True


# -------------------------------- seniority -------------------------------- #
def test_intern_substring_does_not_create_internship():
    exp = parse_experience("Global HR Operations Specialist",
                           "Work with internal teams across international markets.")
    result = classify_seniority("Global HR Operations Specialist",
                                "Work with internal teams across international markets.", exp)
    assert result.level != Seniority.INTERNSHIP


def test_title_junior_but_five_years_required_is_not_junior():
    text = "Minimum 5 years of experience required."
    exp = parse_experience("Business Analyst", text)
    assert classify_seniority("Business Analyst", text, exp).level == Seniority.SENIOR


def test_associate_product_manager_is_not_management():
    exp = parse_experience("Associate Product Manager", "Entry level role.")
    level = classify_seniority("Associate Product Manager", "Entry level role.", exp).level
    assert level not in (Seniority.MANAGER, Seniority.DIRECTOR, Seniority.SENIOR)


# ---------------------------------- alemán --------------------------------- #
@pytest.mark.parametrize("text,expected_min", [
    ("Fluent German is required for this role.", 100),
    ("German is a plus for our DACH clients.", 70),
    ("Alemán deseable, no excluyente.", 50),
    ("Strong analytical skills and teamwork.", 0),
])
def test_german_levels(text, expected_min):
    assert analyze_languages("Analyst", text).german_score >= expected_min


def test_germany_the_country_is_not_the_language():
    result = analyze_languages("Analyst", "Our headquarters are in Germany and Austria.")
    assert result.german_score < 50


# --------------------------------- ubicación -------------------------------- #
@pytest.mark.parametrize("location,minimum", [
    ("San Isidro, Buenos Aires", 95),
    ("Vicente López", 95),
    ("Palermo, CABA", 80),
    ("Córdoba, Argentina", 50),
])
def test_location_priority(location, minimum):
    remote = detect_remote_type(location, None, None)
    assert score_location(location, None, remote).score >= minimum


def test_remote_restricted_to_us_scores_low():
    result = score_location("Remote", "Must be located in the United States.", RemoteType.REMOTE)
    assert result.score < 30


# --------------------------------- prefiltro -------------------------------- #
@pytest.mark.parametrize("title,location,remote,keep", [
    ("Business Analyst", "Gurugram, India", "unknown", False),
    ("Business Analyst", "São Paulo", "remote", False),
    ("Analista Junior", "San Isidro, Buenos Aires", "onsite", True),
    ("Product Analyst", "Remote - LATAM", "remote", True),
    ("Senior Product Manager", "Buenos Aires", "onsite", False),
    ("Associate Product Manager", "Buenos Aires", "onsite", True),
    ("Talent Network", "Buenos Aires", "onsite", False),
])
def test_prefilter(title, location, remote, keep):
    assert should_ingest(title=title, location=location, description=None,
                         remote_type=remote).keep is keep


# ----------------------------------- roles ---------------------------------- #
def test_semantic_match_without_exact_keyword():
    assert match_role("Strategy & Operations Analyst").score >= 80


def test_generic_words_do_not_create_a_match():
    assert match_role("Analista de Mantenimiento Jr").score < 45


def test_engineering_roles_are_downweighted():
    assert match_role("Data Engineer").score < 50
    assert match_role("Software Engineer").score < 40


# ---------------------------------- skills ---------------------------------- #
def test_must_have_vs_nice_to_have():
    result = extract_skills("Analista", "Requisitos:\nExcel avanzado excluyente\n\n"
                                        "Deseable:\nConocimientos de SQL\nPower BI")
    assert "excel" in result.must_have
    assert "sql" in result.nice_to_have and "power bi" in result.nice_to_have


# ------------------------- scoring de punta a punta ------------------------- #
def test_fixtures_match_expectations(sample_jobs, candidate):
    for job in sample_jobs:
        candidate.experience_policy = "strict"
        expect = job.get("expect") or {}
        if "duplicate_of" in expect:
            continue
        scores, sen, exp, lang, loc, role = analyze(job, candidate)
        if "seniority" in expect:
            assert sen.level.value == expect["seniority"], f"{job['id']}: seniority"
        if "eligible" in expect:
            assert scores.eligible is expect["eligible"], (
                f"{job['id']}: elegibilidad ({scores.not_eligible_reason})"
            )
        if "german_min" in expect:
            assert lang.german_score >= expect["german_min"], f"{job['id']}: alemán"
        if "location_min" in expect:
            assert loc.score >= expect["location_min"], f"{job['id']}: ubicación"


def test_graduate_program_outranks_generic_role(sample_jobs, candidate):
    grad = next(j for j in sample_jobs if j["id"] == "graduate_program_target")
    generic = next(j for j in sample_jobs if j["id"] == "commission_only_scam")
    assert analyze(grad, candidate)[0].final_score > analyze(generic, candidate)[0].final_score + 30


def test_preferences_do_not_become_hard_filters(sample_jobs, candidate):
    """§51: en modo equilibrado, un 'preferred' no puede bloquear por sí solo."""
    candidate.experience_policy = "balanced"
    job = next(j for j in sample_jobs if j["id"] == "preferred_not_required")
    scores, *_ = analyze(job, candidate)
    assert scores.eligible is True
    assert not scores.hard_blockers


def test_the_same_job_is_filtered_under_the_strict_policy(sample_jobs, candidate):
    """Y en modo estricto —el que la candidata eligió— sí se descarta."""
    job = dict(next(j for j in sample_jobs if j["id"] == "preferred_not_required"))
    job["policy"] = "strict"
    scores, *_ = analyze(job, candidate)
    assert scores.eligible is False


def test_every_analysis_has_an_explanation(sample_jobs, candidate):
    for job in sample_jobs:
        if "duplicate_of" in (job.get("expect") or {}):
            continue
        scores, *_ = analyze(job, candidate)
        assert scores.summary, f"{job['id']}: falta summary"
        assert scores.why_apply, f"{job['id']}: falta why_apply"
        assert scores.match_reasons or scores.hard_blockers, f"{job['id']}: sin explicación"


# --------------------------- regresiones de negación ------------------------ #
def test_not_required_is_a_preference_not_a_requirement():
    """'Portuguese (not required)' no puede leerse como requisito de portugués."""
    result = analyze_languages(
        "Growth Analyst",
        "Portuguese proficiency (not required, but useful). Advanced English is required.",
    )
    by_code = {l["code"]: l["requirement"] for l in result.languages}
    assert by_code["pt"] == "preferred"
    assert by_code["en"] == "required"


def test_modality_is_read_from_the_title():
    from app.pipeline.location import detect_remote_type as detect

    assert detect("Buenos Aires", None, None, "Growth Analyst (Hybrid)") == RemoteType.HYBRID
    assert detect("Argentina", None, None, "Analyst (Remote)") == RemoteType.REMOTE


# ------------------ foco real en primer empleo (política estricta) ----------- #
ENTRY_ONLY_TITLES = [
    "Actuarial Services - Experienced Associate",
    "IT Audit - Experienced Associate",
    "Associate Managing Consultant, Advisors & Consulting",
    "Strategy & Consulting | Management Consultant",
    "Mining Client Group Leader",
    "ARG Project Leader-2",
    "Named Account Executive",
]


@pytest.mark.parametrize("title", ENTRY_ONLY_TITLES)
def test_titles_that_imply_previous_experience_are_not_entry_level(title):
    """'Experienced Associate' o 'Managing Consultant' no son un primer empleo."""
    exp = parse_experience(title, "Join our team.")
    level = classify_seniority(title, "Join our team.", exp).level
    assert level not in (
        Seniority.INTERNSHIP, Seniority.TRAINEE, Seniority.GRADUATE,
        Seniority.ENTRY_LEVEL, Seniority.JUNIOR,
    ), f"{title} quedó como {level.value}"


@pytest.mark.parametrize("title", [
    "Junior - SAP FI", "Associate - Transaction Services",
    "Associate Product Manager", "Graduate Program - Business Analyst",
    "Management Trainee", "Business Development Representative",
])
def test_real_entry_level_titles_survive(title):
    exp = parse_experience(title, "We welcome recent graduates.")
    level = classify_seniority(title, "We welcome recent graduates.", exp).level
    assert level not in (Seniority.SEMI_SENIOR, Seniority.SENIOR,
                         Seniority.MANAGER, Seniority.DIRECTOR), f"{title} -> {level.value}"


def _score(job, candidate):
    return analyze(job, candidate)[0]


def test_strict_policy_rejects_stated_experience(candidate):
    candidate.experience_policy = "strict"
    job = {"title": "Business Analyst", "company": "X", "location": "Buenos Aires",
           "remote_hint": "onsite",
           "description": "Requisitos: 2 años de experiencia en posiciones similares."}
    result = _score(job, candidate)
    assert result.eligible is False
    assert "experiencia" in (result.not_eligible_reason or "")


def test_strict_policy_rejects_a_preference_of_one_year(candidate):
    """La usuaria pidió foco en sin experiencia: 1 año 'deseable' también sobra."""
    candidate.experience_policy = "strict"
    job = {"title": "Analyst", "company": "X", "location": "Buenos Aires",
           "remote_hint": "onsite",
           "description": "Deseable 1 año de experiencia. Excel avanzado."}
    assert _score(job, candidate).eligible is False


def test_open_policy_keeps_what_strict_rejects(candidate):
    """La política es configurable: no se le impone un criterio único."""
    job = {"title": "Business Analyst", "company": "X", "location": "Buenos Aires",
           "remote_hint": "onsite",
           "description": "Requisitos: 2 años de experiencia en posiciones similares."}
    candidate.experience_policy = "strict"
    assert _score(job, candidate).eligible is False
    candidate.experience_policy = "open"
    assert _score(job, candidate).eligible is True


def test_no_experience_jobs_get_a_boost(candidate):
    candidate.experience_policy = "strict"
    job = {"title": "Analista Junior", "company": "X", "location": "Buenos Aires",
           "remote_hint": "onsite",
           "description": "No se requiere experiencia previa. Buscamos recién graduados."}
    result = _score(job, candidate)
    assert result.eligible is True
    assert any(b["key"] == "no_experience_required" for b in result.boosts)


def test_no_experience_outranks_one_that_asks_for_experience(candidate):
    candidate.experience_policy = "balanced"
    base = {"company": "X", "location": "Buenos Aires", "remote_hint": "onsite"}
    sin_exp = _score({**base, "title": "Analista Junior",
                      "description": "No se requiere experiencia previa. Excel avanzado."},
                     candidate)
    con_exp = _score({**base, "title": "Analista Junior",
                      "description": "Se requieren 2 años de experiencia. Excel avanzado."},
                     candidate)
    assert sin_exp.final_score > con_exp.final_score


def test_job_fairs_and_talent_pools_are_not_recommended(candidate):
    for title in ["Feria TalentoIT - Potrero Empleos", "Banco de Talentos",
                  "Join our talent network!"]:
        job = {"title": title, "company": "X", "location": "Buenos Aires",
               "remote_hint": "onsite", "description": "Dejanos tu CV."}
        assert _score(job, candidate).eligible is False, title


# ------------------------- resumen extraído del aviso ----------------------- #
AVISO_CON_SECCIONES = """Line of Service
Advisory

Management Level
Associate

Job Description & Summary

Somos PwC Argentina, firma líder en el mercado de servicios profesionales.

Sumate como Junior SAP FI para formar parte de nuestro equipo y participar en
diferentes proyectos de implementación.

Principales desafíos

- Participar en proyectos de SAP FI, colaborando en el análisis de procesos.
- Brindar soporte post go-live respondiendo preguntas de usuarios.

Requisitos

- Formación académica: Administración, Finanzas o carreras afines.
- Inglés intermedio.

Deseable

- Certificado en SAP FI.

Beneficios

- Cobertura médica y días de estudio.
"""


def test_summary_extracts_each_section():
    from app.pipeline.summarize import summarize_description

    d = summarize_description(AVISO_CON_SECCIONES)
    assert d.cobertura == "completo"
    assert len(d.responsabilidades) == 2
    assert len(d.requisitos) == 2
    assert d.deseables and "SAP FI" in d.deseables[0]
    assert d.beneficios and "médica" in d.beneficios[0]


def test_summary_prefers_the_role_over_the_company_boilerplate():
    """'Somos líderes en...' no ayuda a decidir si aplicar; la frase del puesto sí."""
    from app.pipeline.summarize import summarize_description

    overview = summarize_description(AVISO_CON_SECCIONES).overview
    assert "Sumate como Junior SAP FI" in overview
    assert not overview.startswith("Somos PwC")


def test_summary_drops_ats_metadata():
    from app.pipeline.summarize import summarize_description

    d = summarize_description(AVISO_CON_SECCIONES)
    todo = " ".join([d.overview, *d.responsabilidades, *d.requisitos])
    assert "Line of Service" not in todo
    assert "Management Level" not in todo


def test_summary_never_invents_text():
    """El resumen es un extracto: cada frase tiene que estar en el aviso original."""
    from app.pipeline.summarize import summarize_description

    d = summarize_description(AVISO_CON_SECCIONES)
    for item in d.responsabilidades + d.requisitos + d.deseables + d.beneficios:
        assert item.rstrip("…") in AVISO_CON_SECCIONES, f"texto inventado: {item}"


def test_summary_handles_a_missing_description():
    from app.pipeline.summarize import summarize_description

    for entrada in (None, "", "   ", "corto"):
        d = summarize_description(entrada)
        assert d.cobertura == "sin_descripcion"
        assert d.tiene_contenido is False


def test_sort_columns_cover_every_score_shown_in_the_ui():
    """Cada puntaje visible en una tarjeta debe poder usarse para ordenar."""
    from app.api.routes.jobs import ORDER_COLUMNS

    assert {"final_score", "fit_score", "company_score", "career_score",
            "german", "date", "published"} == set(ORDER_COLUMNS)


# --------------------------------------------------------------------------- #
# EXPERIENCIA: los marcadores se comparan con límites de palabra
# "0 years" matcheaba dentro de "more than 160 years of history" (la reseña
# corporativa de BBVA), y un puesto que pedía 2 años quedaba como "no requiere
# experiencia" y aparecía recomendado. Misma clase de bug que "intern" dentro
# de "international".
# --------------------------------------------------------------------------- #
def test_la_antiguedad_de_la_empresa_no_se_lee_como_cero_experiencia():
    from app.pipeline.experience import parse_experience

    descripcion = (
        "BBVA is a global company with more than 160 years of history that "
        "operates in more than 25 countries. "
        "Experiencia mínima de 2 años en posiciones vinculadas a contracargos, "
        "fraude, adquirencia, medios de pago o fintech."
    )

    req = parse_experience("Analista de Contracargos", descripcion)

    assert req.min_years == 2.0
    assert req.accepts_no_experience is False


def test_sigue_detectando_cero_experiencia_cuando_de_verdad_lo_dice():
    from app.pipeline.experience import parse_experience

    req = parse_experience("Analista Junior", "We ask for 0 years of experience. Sin experiencia previa.")

    assert req.accepts_no_experience is True
    assert req.min_years == 0.0


def test_un_puesto_que_pide_anos_no_queda_elegible():
    """El caso que reportó el usuario: avisos de 4 años apareciendo como aplicables."""
    from app.pipeline.experience import parse_experience

    req = parse_experience(
        "Account Manager",
        "Somos una empresa con 100 years of excellence. "
        "Requiere un mínimo de 4 años de experiencia en ventas B2B.",
    )

    assert req.min_years == 4.0
    assert req.accepts_no_experience is False
