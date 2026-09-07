"""Tests de la ingesta de alertas por email y de la importación manual."""
from __future__ import annotations

import pathlib

import pytest

from app.services.importer import (
    NO_FETCH_DOMAINS,
    _domain_blocked,
    _looks_like_a_posting,
    detect_ats,
)
from app.sources.base import ComplianceLevel
from app.sources.email_alerts import (
    PROVIDERS,
    EmailAlertsSource,
    clean_url,
    extract_job_id,
    parse_alert_html,
)
from app.sources.registry import SOURCE_CLASSES

EMAILS = pathlib.Path(__file__).parent / "fixtures" / "emails"


def load(name: str) -> str:
    return (EMAILS / f"{name}.html").read_text(encoding="utf-8")


# ------------------------------ parseo de mails ----------------------------- #
@pytest.mark.parametrize("provider_key,expected", [
    ("linkedin", 2), ("indeed", 2), ("bumeran", 2),
])
def test_alert_emails_yield_the_expected_jobs(provider_key, expected):
    jobs = parse_alert_html(load(provider_key), PROVIDERS[provider_key])
    assert len(jobs) == expected


def test_linkedin_alert_extracts_title_company_and_location():
    jobs = parse_alert_html(load("linkedin"), PROVIDERS["linkedin"])
    by_title = {j.title: j for j in jobs}
    job = by_title["Junior Business Analyst"]
    assert job.company == "Fintech Uno"
    assert "Vicente López" in (job.location or "")
    assert job.source_job_id == "linkedin:4012345678"


def test_navigation_links_are_not_treated_as_jobs():
    """'Ver todos los empleos' y 'Darse de baja' no son puestos."""
    titles = {j.title.lower() for j in parse_alert_html(load("linkedin"), PROVIDERS["linkedin"])}
    assert "ver todos los empleos" not in titles
    assert "darse de baja" not in titles
    assert "postularme" not in titles


def test_apply_link_does_not_duplicate_the_job():
    """El link 'Postularme' apunta al mismo id que el título: es un solo aviso."""
    jobs = parse_alert_html(load("linkedin"), PROVIDERS["linkedin"])
    ids = [j.source_job_id for j in jobs]
    assert len(ids) == len(set(ids))


def test_tracking_parameters_are_stripped():
    """Sin esto, el mismo aviso entraría distinto cada día."""
    jobs = parse_alert_html(load("linkedin"), PROVIDERS["linkedin"])
    for job in jobs:
        assert "trackingId" not in job.url
        assert "trk=" not in job.url


def test_clean_url_keeps_the_meaningful_query():
    provider = PROVIDERS["indeed"]
    cleaned = clean_url("https://ar.indeed.com/viewjob?jk=abc123&trk=eml", provider)
    assert "jk=abc123" in cleaned


@pytest.mark.parametrize("provider_key,url,expected", [
    ("linkedin", "https://www.linkedin.com/comm/jobs/view/4012345678/?x=1", "4012345678"),
    ("indeed", "https://ar.indeed.com/rc/clk?jk=a1b2c3", "a1b2c3"),
    ("bumeran", "https://www.bumeran.com.ar/empleos/analista-1116789012.html", "1116789012"),
])
def test_job_id_extraction(provider_key, url, expected):
    assert extract_job_id(url, PROVIDERS[provider_key]) == expected


def test_jobs_from_email_are_marked_as_needing_detail():
    """El mail no trae la descripción: el análisis debe saberlo."""
    for job in parse_alert_html(load("indeed"), PROVIDERS["indeed"]):
        assert job.raw["needs_detail"] is True
        assert job.description is None


# ------------------------------- cumplimiento ------------------------------- #
def test_email_source_is_registered_and_off_by_default():
    assert "email_alerts" in SOURCE_CLASSES
    assert EmailAlertsSource.enabled_by_default is False
    assert EmailAlertsSource.compliance == ComplianceLevel.USER_INBOX


def test_email_source_covers_the_restricted_portals():
    assert {"linkedin", "indeed", "bumeran", "zonajobs", "glassdoor"} == set(PROVIDERS)


@pytest.mark.asyncio
async def test_email_source_does_nothing_without_imap_configured():
    from app.sources.base import SourceTarget

    source = EmailAlertsSource()
    assert source.default_targets() == []
    assert await source.search_jobs(SourceTarget("inbox", "inbox")) == []
    healthy, detail = await source.health_check()
    assert healthy is True and "deshabilitada" in detail


# -------------------------------- importación ------------------------------- #
@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs/view/4012345678/",
    "https://ar.indeed.com/viewjob?jk=abc",
    "https://www.bumeran.com.ar/empleos/analista-1.html",
    "https://www.glassdoor.com.ar/job-listing/x",
    "https://ar.linkedin.com/jobs/view/1",
])
def test_restricted_domains_are_never_fetched(url):
    assert _domain_blocked(url) is True


@pytest.mark.parametrize("url", [
    "https://job-boards.greenhouse.io/ebanx/jobs/123",
    "https://careers.example.com/jobs/1",
    "https://notlinkedin.com/jobs/1",
])
def test_allowed_domains_are_fetchable(url):
    assert _domain_blocked(url) is False


@pytest.mark.parametrize("url,expected", [
    ("https://job-boards.greenhouse.io/ebanx/jobs/7645174003", ("greenhouse", "ebanx", "7645174003")),
    ("https://boards.greenhouse.io/datadog/jobs/1234567", ("greenhouse", "datadog", "1234567")),
    ("https://jobs.lever.co/kavak/abcdef01-2345-6789-abcd-ef0123456789",
     ("lever", "kavak", "abcdef01-2345-6789-abcd-ef0123456789")),
    ("https://jobs.smartrecruiters.com/BoschGroup/744000082222",
     ("smartrecruiters", "BoschGroup", "744000082222")),
    ("https://www.linkedin.com/jobs/view/4012345678/", None),
])
def test_ats_urls_are_routed_to_their_public_api(url, expected):
    assert detect_ats(url) == expected


@pytest.mark.parametrize("title,text,expected", [
    ("Junior Business Analyst",
     "Lo que buscamos: graduado. Tus tareas: análisis. Inglés avanzado excluyente.", True),
    ("Join EBANX! - Discover the Careers Portal",
     "apply now to our open positions and discover our careers", False),
    ("Trabajá con nosotros", "Sumate a nuestro equipo. Ofrecemos beneficios y modalidad híbrida.", False),
])
def test_portal_pages_are_not_imported_as_jobs(title, text, expected):
    assert _looks_like_a_posting(text, title) is expected


def test_no_fetch_domains_cover_every_restricted_portal():
    for domain in ("linkedin.com", "indeed.com", "bumeran.com", "zonajobs.com", "glassdoor.com"):
        assert domain in NO_FETCH_DOMAINS


# --------------------------- detección de ATS ------------------------------- #
@pytest.mark.parametrize("blob,expected_type", [
    ("https://boards.greenhouse.io/ebanx/jobs", "greenhouse"),
    ("https://accenture.wd103.myworkdayjobs.com/en-US/AccentureCareers", "workday"),
    ("https://ejig.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions",
     "oracle_recruiting"),
    ("https://bcg.eightfold.ai/careers", "eightfold"),
    ("https://jobs.lever.co/kavak", "lever"),
])
def test_ats_fingerprints(blob, expected_type):
    from app.services.ats_detector import fingerprint

    hit = fingerprint(blob)
    assert hit is not None and hit[0] == expected_type


def test_workday_config_is_built_as_tenant_site_host():
    from app.services.ats_detector import build_config, fingerprint

    ats, groups = fingerprint("https://accenture.wd103.myworkdayjobs.com/en-US/AccentureCareers")
    token, careers = build_config(ats, groups, "")
    assert token == "accenture"
    assert careers == "accenture|AccentureCareers|wd103"


def test_oracle_config_is_built_as_host_site():
    from app.services.ats_detector import build_config, fingerprint

    url = "https://ejig.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/x"
    ats, groups = fingerprint(url)
    _, careers = build_config(ats, groups, "")
    assert careers == "https://ejig.fa.em2.oraclecloud.com|CX_1"


def test_known_platforms_without_connector_are_reported_not_hidden():
    """Es más útil saber que usa Avature a que diga 'desconocido'."""
    from app.services.ats_detector import fingerprint_unsupported

    hit = fingerprint_unsupported("https://pepsico.avature.net/careers")
    assert hit is not None and hit[0] == "avature"
