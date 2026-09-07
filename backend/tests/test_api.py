"""Tests de la API con base efímera."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """La base de test la fija conftest antes de importar la app."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_profile_is_seeded_with_the_candidate(client):
    profile = client.get("/api/profile").json()
    assert "Negocios Digitales" in profile["degree"]
    assert "San Andrés" in profile["university"]
    assert {l["code"] for l in profile["languages"]} >= {"es", "en", "de"}
    assert profile["years_experience"] == 0.0
    assert profile["city"] == "San Isidro"


def test_profile_can_be_edited(client):
    response = client.put("/api/profile", json={"skills": ["excel", "sql", "tableau"],
                                                "city": "Martínez"})
    assert response.status_code == 200
    assert response.json()["city"] == "Martínez"
    client.put("/api/profile", json={"city": "San Isidro"})


def test_target_companies_are_seeded(client):
    companies = client.get("/api/companies").json()
    names = {c["name"] for c in companies}
    assert len(companies) >= 50
    assert {"Mercado Libre", "SAP", "Bosch", "JPMorgan Chase"} <= names
    assert any(c["german_relevant"] for c in companies)


def test_target_company_can_be_added_and_removed(client):
    created = client.post("/api/companies", json={"name": "Empresa Nueva Test",
                                                  "ats_type": "greenhouse",
                                                  "ats_token": "test"}).json()
    assert created["name"] == "Empresa Nueva Test"
    assert client.delete(f"/api/companies/{created['id']}").json()["ok"] is True


def test_sources_catalog_and_compliance(client):
    health = client.get("/api/sources/health").json()
    by_key = {s["key"]: s for s in health["sources"]}
    assert by_key["greenhouse"]["enabled"] is True
    # Los portales restringidos vienen apagados y con su nota de política
    assert by_key["linkedin"]["enabled"] is False
    assert by_key["linkedin"]["compliance_note"]
    assert by_key["indeed"]["enabled"] is False


def test_source_can_be_toggled(client):
    assert client.patch("/api/sources/jobicy", json={"enabled": False}).json()["enabled"] is False
    assert client.patch("/api/sources/jobicy", json={"enabled": True}).json()["enabled"] is True


def test_search_links_for_restricted_portals(client):
    data = client.get("/api/sources/search-links").json()
    assert data["links"]
    assert {l["portal"] for l in data["links"]} >= {"linkedin", "indeed"}


def test_dashboard_endpoints(client):
    today = client.get("/api/dashboard/today").json()
    assert {"nuevas_hoy", "recomendadas", "aplicar_ya", "empresas_objetivo"} <= set(today)
    stats = client.get("/api/dashboard/stats").json()
    assert "promedio_fit" in stats and "aplicaciones" in stats


def test_jobs_listing_is_empty_before_a_run(client):
    assert client.get("/api/jobs").json()["total"] == 0


def test_top_picks_has_all_categories(client):
    buckets = client.get("/api/jobs/top-picks").json()["buckets"]
    keys = {b["key"] for b in buckets}
    assert {"aplicar_hoy", "empresas_sonadas", "aleman", "graduate",
            "product_tech", "business", "data", "finance"} == keys


def test_config_exposes_weights(client):
    config = client.get("/api/config").json()
    assert config["preferences"]["fit_weights"]["seniority"] == 25.0
    assert config["preferences"]["display"]["min_display_score"] == 70.0


def test_weights_can_be_changed(client):
    response = client.put("/api/config/display", json={"value": {"min_display_score": 65.0}})
    assert response.json()["display"]["min_display_score"] == 65.0
    client.put("/api/config/display", json={"value": {"min_display_score": 70.0}})


def test_personalization_is_transparent(client):
    data = client.get("/api/config/personalization").json()
    assert "ajustes" in data and "nota" in data


def test_unknown_config_key_is_rejected(client):
    assert client.put("/api/config/inventada", json={"value": {}}).status_code == 404


def test_missing_job_returns_404(client):
    assert client.get("/api/jobs/999999").status_code == 404


def test_radar_separates_what_is_queried_from_what_is_not(client):
    """La app tiene que decir con precisión qué mira y qué no."""
    radar = client.get("/api/companies/radar").json()
    assert radar["empresas_consultadas"] > 0
    assert radar["total_objetivos"] >= radar["empresas_consultadas"]
    assert radar["agregadores"], "faltan los agregadores"

    consultadas = {c["name"] for g in radar["por_ats"] for c in g["companies"]}
    sin_conector = {c["name"] for c in radar["sin_conector"]}
    assert consultadas, "ninguna empresa se está consultando"
    assert not (consultadas & sin_conector), "una empresa no puede estar en ambos grupos"


def test_every_queried_company_has_a_connector(client):
    radar = client.get("/api/companies/radar").json()
    companies = {c["name"]: c for c in client.get("/api/companies").json()}
    for group in radar["por_ats"]:
        for entry in group["companies"]:
            assert companies[entry["name"]]["ats_type"] == group["ats"]


def test_companies_without_a_connector_are_reported_not_silently_ignored(client):
    """36 empresas figuraban como objetivo sin que nadie las consultara."""
    radar = client.get("/api/companies/radar").json()
    for entry in radar["sin_conector"]:
        assert entry["name"]


def test_desktop_notification_is_a_real_channel(client):
    """La notificación de escritorio no depende de ninguna cuenta ni servicio."""
    config = client.get("/api/config").json()
    assert "notificaciones" in config
    assert "escritorio" in config["notificaciones"]


def test_companies_overview_counts_real_jobs(client):
    """La sección Empresas necesita conteos reales, no la lista pelada."""
    empresas = client.get("/api/companies/overview").json()
    assert empresas
    campos = {"company_id", "name", "total_jobs", "recommended_jobs", "new_today"}
    assert campos <= set(empresas[0])
    for empresa in empresas:
        assert empresa["recommended_jobs"] <= empresa["eligible_jobs"] <= empresa["total_jobs"]


def test_companies_overview_can_hide_the_empty_ones(client):
    todas = client.get("/api/companies/overview").json()
    con_avisos = client.get("/api/companies/overview?only_with_jobs=true").json()
    assert len(con_avisos) <= len(todas)
    assert all(c["total_jobs"] > 0 for c in con_avisos)


def test_jobs_can_be_filtered_by_company_id(client):
    """Entrar a una empresa y ver sus avisos: filtro exacto, no por nombre."""
    response = client.get("/api/jobs?company_id=999999&min_score=0")
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.parametrize("campo", [
    "final_score", "fit_score", "company_score", "career_score",
    "german", "date", "published",
])
def test_every_sort_field_works_in_both_directions(client, campo):
    for direccion in ("desc", "asc"):
        r = client.get(f"/api/jobs?min_score=0&order_by={campo}&order_dir={direccion}")
        assert r.status_code == 200, f"{campo}/{direccion}"


def test_an_unknown_sort_field_falls_back_instead_of_failing(client):
    r = client.get("/api/jobs?min_score=0&order_by=inventado&order_dir=raro")
    assert r.status_code == 200


def test_top_picks_accepts_the_same_sort(client):
    r = client.get("/api/jobs/top-picks?order_by=fit_score&order_dir=asc")
    assert r.status_code == 200
    assert "buckets" in r.json()


def test_sorting_by_age_works_when_the_source_omits_the_publication_date(client):
    """SuccessFactors no informa fecha de publicación en NINGÚN aviso.

    Sin respaldo, ordenar por esa columna dejaba la lista en el orden del
    desempate por puntaje: el usuario veía "ayer" antes que "hace 2 h".
    """
    from sqlalchemy import select

    from app.api.routes.jobs import ORDER_COLUMNS
    from app.models import Job

    columna = ORDER_COLUMNS["published"]
    # La columna tiene que ser un COALESCE, no la fecha pelada
    assert "coalesce" in str(columna).lower()
    assert "publication_date" in str(columna)
    assert "first_seen_date" in str(columna)
    del select, Job


def test_age_sort_returns_results_in_both_directions(client):
    for direccion in ("desc", "asc"):
        r = client.get(f"/api/jobs?min_score=0&order_by=published&order_dir={direccion}")
        assert r.status_code == 200


# --------------------------------------------------------------------------- #
# DISPARO DE BÚSQUEDA
# Una corrida completa tarda varios minutos. El endpoint tiene que contestar
# enseguida y dejar la corrida en segundo plano: si espera, el proxy del
# frontend corta por timeout y al usuario le aparece un 500 aunque el pipeline
# esté funcionando bien.
# --------------------------------------------------------------------------- #
def test_disparar_busqueda_contesta_enseguida_sin_esperar_la_corrida(client, monkeypatch):
    import asyncio

    import app.api.routes.misc as misc

    arrancada = asyncio.Event()

    async def pipeline_lento(*_args, **_kwargs):
        arrancada.set()
        await asyncio.sleep(30)          # más de lo que el test tolera esperar
        return {}

    monkeypatch.setattr(misc, "run_pipeline", pipeline_lento)
    monkeypatch.setattr(misc, "esta_corriendo", lambda: False)

    respuesta = client.post("/api/runs", json={"notify": False})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "running"
    assert cuerpo["mensaje"]
    assert arrancada.is_set(), "la corrida tiene que haber arrancado en segundo plano"


def test_disparar_busqueda_rechaza_una_segunda_corrida_simultanea(client, monkeypatch):
    import app.api.routes.misc as misc

    monkeypatch.setattr(misc, "esta_corriendo", lambda: True)

    respuesta = client.post("/api/runs", json={"notify": False})

    assert respuesta.status_code == 409
    assert "curso" in respuesta.json()["detail"].lower()
