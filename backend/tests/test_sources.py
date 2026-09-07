"""Tests de los adaptadores de fuentes con payloads reales anonimizados."""
from __future__ import annotations

import pytest

from app.sources.ats import (
    AshbySource,
    GreenhouseSource,
    LeverSource,
    SmartRecruitersSource,
    html_to_text,
    parse_dt,
)
from app.sources.base import RawJob, SourceTarget
from app.sources.registry import COMPANY_DRIVEN, SOURCE_CLASSES
from app.sources.restricted import LinkedInSource, SavedSearchLinksSource


class FakeSource(GreenhouseSource):
    """Fuente que falla siempre, para verificar el aislamiento de errores."""

    async def search_jobs(self, target):
        raise RuntimeError("la fuente se cayó")


def test_registry_has_every_required_adapter():
    required = {"linkedin", "indeed", "bumeran", "zonajobs", "greenhouse", "lever",
                "workday", "successfactors", "company_careers", "ashby",
                "smartrecruiters", "workable"}
    assert required <= set(SOURCE_CLASSES)


def test_every_source_implements_the_contract():
    for key, cls in SOURCE_CLASSES.items():
        instance = cls()
        assert hasattr(instance, "search_jobs"), key
        assert hasattr(instance, "fetch_job"), key
        assert hasattr(instance, "normalize_job"), key
        assert hasattr(instance, "health_check"), key


def test_company_driven_sources_are_registered():
    assert COMPANY_DRIVEN <= set(SOURCE_CLASSES)


@pytest.mark.asyncio
async def test_a_failing_source_does_not_raise():
    """§35: una fuente rota no puede romper la corrida."""
    result = await FakeSource().run(SourceTarget("x", "X", {"token": "x"}))
    assert result.status == "error"
    assert result.jobs == []
    assert "la fuente se cayó" in result.error


def test_restricted_sources_are_disabled_by_default():
    for cls in (LinkedInSource,):
        assert cls.enabled_by_default is False
        assert cls.compliance == "restricted"
        assert cls.compliance_note


@pytest.mark.asyncio
async def test_restricted_source_returns_nothing_without_credentials():
    assert await LinkedInSource().search_jobs(SourceTarget("q", "q")) == []


def test_saved_search_links_are_built_for_every_portal():
    links = SavedSearchLinksSource.build_links(["Business Analyst"])
    portals = {l["portal"] for l in links}
    assert {"linkedin", "indeed", "bumeran", "zonajobs"} <= portals
    assert all(l["url"].startswith("https://") for l in links)


def test_html_to_text_strips_markup():
    assert html_to_text("<p>Hola <b>mundo</b></p><script>x=1</script>") == "Hola mundo"


@pytest.mark.parametrize("value", ["2026-09-01T10:00:00Z", "2026-09-01", 1756704000])
def test_parse_dt_handles_formats(value):
    assert parse_dt(value) is not None


def test_greenhouse_normalizes_escaped_html():
    source = GreenhouseSource()
    raw = RawJob(source="greenhouse", source_job_id="1", url="u", title="T", company="C",
                 description="&lt;p&gt;Hola&lt;/p&gt;")
    assert source.normalize_job(raw).description == "Hola"


def test_source_labels_and_compliance_notes_exist():
    for key, cls in SOURCE_CLASSES.items():
        assert cls.label, key
        assert cls.compliance, key


@pytest.mark.parametrize("cls", [GreenhouseSource, LeverSource, AshbySource, SmartRecruitersSource])
def test_ats_sources_use_public_apis(cls):
    assert cls.compliance == "public_ats_api"


# ------------------------- ATS de grandes empresas -------------------------- #
def test_enterprise_sources_are_registered():
    """Las multinacionales casi nunca usan Greenhouse: hacen falta estos ATS."""
    assert {"workday", "oracle_recruiting", "eightfold"} <= set(SOURCE_CLASSES)


@pytest.mark.parametrize("key", ["workday", "oracle_recruiting", "eightfold"])
def test_enterprise_sources_use_public_apis(key):
    cls = SOURCE_CLASSES[key]
    assert cls.compliance == "public_ats_api"
    assert cls.requires_config is True


def test_amazon_source_is_registered():
    assert "amazon_jobs" in SOURCE_CLASSES
    assert SOURCE_CLASSES["amazon_jobs"].compliance == "public_ats_api"
    assert SOURCE_CLASSES["amazon_jobs"]().default_targets()


def test_seed_connectors_are_well_formed():
    """Un conector mal cargado se traduce en una empresa que nadie consulta."""
    from app.data.target_companies import SEED_COMPANIES

    for company in SEED_COMPANIES:
        ats = company.get("ats_type")
        if not ats:
            continue
        assert ats in SOURCE_CLASSES, f"{company['name']}: ATS desconocido '{ats}'"
        if ats == "workday":
            parts = (company.get("careers_url") or "").split("|")
            assert len(parts) == 3, f"{company['name']}: Workday necesita tenant|site|host"
        elif ats == "oracle_recruiting":
            assert (company.get("careers_url") or "").startswith("http"), company["name"]
        elif ats in ("greenhouse", "lever", "ashby", "smartrecruiters", "eightfold"):
            assert company.get("ats_token"), f"{company['name']}: falta ats_token"


def test_eightfold_supports_own_domain_apis():
    """Mercado Libre sirve la API de Eightfold desde su propio dominio."""
    from app.sources.enterprise import EightfoldSource

    source = EightfoldSource()
    raw = source._to_raw(
        {"id": 42474451, "name": "Analista Contable",
         "locations": ["Buenos Aires,Argentina"], "workLocationOption": "hybrid",
         "postedTs": 1788270973, "department": "Fintech"},
        token="meli", company="Mercado Libre",
        base_url="https://careers-meli.mercadolibre.com",
    )
    assert raw.title == "Analista Contable"
    assert "Argentina" in (raw.location or "")
    assert raw.remote_hint == "hybrid"
    assert raw.url == "https://careers-meli.mercadolibre.com/es/positions?id=42474451"
    assert raw.raw["needs_detail"] is True


def test_rendered_source_is_registered_and_off_by_default():
    from app.sources.rendered import RenderedCareerSource

    assert RenderedCareerSource.enabled_by_default is False
    assert RenderedCareerSource.compliance == "public_html"
    assert "robots.txt" in RenderedCareerSource.compliance_note


def test_rendered_source_extracts_jobs_from_captured_json():
    """El renderizador captura el JSON que pide la propia página."""
    from app.sources.rendered import RenderedSite, parse_generic_json

    site = RenderedSite("x", "Empresa X", "https://x.com/jobs")
    payloads = [{"data": {"results": [
        {"id": "77", "title": "Business Analyst Trainee",
         "location": "Buenos Aires, Argentina", "url": "/jobs/77"},
        {"id": "78", "name": "Nada"},
    ]}}]
    jobs = parse_generic_json(payloads, site, "https://x.com/jobs")
    by_title = {j.title: j for j in jobs}
    assert "Business Analyst Trainee" in by_title
    assert by_title["Business Analyst Trainee"].url == "https://x.com/jobs/77"
    assert by_title["Business Analyst Trainee"].company == "Empresa X"


def test_phenom_source_is_registered():
    """Phenom es el career site de varias multinacionales a la vez."""
    assert "phenom" in SOURCE_CLASSES
    assert SOURCE_CLASSES["phenom"].compliance == "public_ats_api"


def test_phenom_parses_its_nested_payload():
    """La API de Phenom envuelve cada aviso en {"data": {...}}."""
    from app.sources.enterprise import PhenomSource

    raw = PhenomSource()._to_raw(
        {"slug": "103485", "title": "Platform Lead", "city": "Buenos Aires",
         "country": "Argentina", "full_location": "Buenos Aires, Argentina",
         "employment_type": "FULL_TIME", "posted_date": "2026-09-04T20:38:00+0000",
         "apply_url": "https://spanish-careers-aon.icims.com/jobs/103485/login",
         "categories": [{"name": "IT Global Technology Leadership"}],
         "description": "<p>Sobre el rol</p>", "hiring_organization": "Aon Corporation"},
        host="jobs.aon.com", company="Aon",
    )
    assert raw is not None
    assert raw.title == "Platform Lead"
    assert raw.location == "Buenos Aires, Argentina"
    assert raw.company == "Aon Corporation"
    assert raw.apply_url.endswith("/103485/login")
    assert raw.department == "IT Global Technology Leadership"
    assert raw.description == "Sobre el rol"


def test_phenom_skips_rows_without_a_title():
    from app.sources.enterprise import PhenomSource

    assert PhenomSource()._to_raw({"slug": "1"}, host="x.com", company="X") is None


def test_the_detector_now_supports_phenom():
    """Phenom dejó de ser 'reconocida sin conector'."""
    from app.services.ats_detector import SUPPORTED_LABEL, fingerprint, fingerprint_unsupported

    assert "phenom" in SUPPORTED_LABEL
    assert fingerprint_unsupported("https://x.com/phenompeople.js") is None
    hit = fingerprint("https://careers.x.com/static/phenompeople/app.js")
    assert hit is not None and hit[0] == "phenom"
