"""Adaptadores para los ATS que usan las grandes empresas.

Ninguno es scraping: son las mismas APIs JSON públicas que consume la propia
página de carreras de cada compañía. Cubren el hueco más importante del sistema,
porque las multinacionales (bancos, consultoras, consumo masivo) casi nunca usan
Greenhouse o Lever.
"""
from __future__ import annotations

from app.sources.ats import html_to_text, parse_dt
from app.sources.base import (
    BaseJobSource,
    ComplianceLevel,
    RawJob,
    SourceKind,
    SourceTarget,
)


class OracleRecruitingSource(BaseJobSource):
    """Oracle Recruiting Cloud (Oracle Fusion HCM).

    Lo usan Oracle, ICBC, muchos bancos y buena parte de las empresas que
    corren Fusion. Se configura con `careers_url` en formato `host|site`,
    por ejemplo: `https://eeho.fa.us2.oraclecloud.com|CX_1`.
    """

    key = "oracle_recruiting"
    label = "Oracle Recruiting Cloud"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = (
        "API REST pública (hcmRestApi) que la propia career page de la empresa consume. Sin auth."
    )
    requires_config = True

    PAGE_SIZE = 50

    def _list_url(self, host: str, site: str, location: str, offset: int) -> str:
        return (
            f"{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            f"?onlyData=true&expand=requisitionList.secondaryLocations"
            f"&finder=findReqs;siteNumber={site},limit={self.PAGE_SIZE},offset={offset},"
            f"location={location},sortBy=POSTING_DATES_DESC"
        )

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        params = target.params
        host = params["host"].rstrip("/")
        site = params.get("site", "CX_1")
        location = params.get("location", "Argentina")
        company = params.get("company") or host

        out: list[RawJob] = []
        offset = 0
        while offset <= params.get("max_offset", 150):
            data = await self._get_json(self._list_url(host, site, location, offset))
            items = data.get("items") or []
            if not items:
                break
            block = items[0]
            requisitions = block.get("requisitionList") or []
            for req in requisitions:
                out.append(self._to_raw(req, host, site, company))
            if len(requisitions) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE

        # El listado de Oracle trae descripciones recortadas (JPMorgan devuelve
        # ~200 caracteres): sin el detalle, el análisis se queda sin material.
        # Se acota el gasto con un tope de llamadas por corrida.
        budget = params.get("detail_budget", 60)
        for job in out:
            if budget <= 0:
                break
            if job.description and len(job.description) >= 600:
                continue
            await self._enrich(job, host, site)
            budget -= 1
        return out

    def _to_raw(self, req: dict, host: str, site: str, company: str) -> RawJob:
        job_id = str(req.get("Id"))
        secondary = ", ".join(
            s.get("Name", "") for s in (req.get("secondaryLocations") or []) if s.get("Name")
        )
        parts = [
            html_to_text(req.get(field))
            for field in ("ShortDescriptionStr", "ExternalResponsibilitiesStr",
                          "ExternalQualificationsStr")
            if req.get(field)
        ]
        return RawJob(
            source=self.key,
            source_job_id=job_id,
            url=f"{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{job_id}",
            apply_url=f"{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{job_id}/apply",
            title=req.get("Title", ""),
            company=company,
            location=req.get("PrimaryLocation") or secondary or None,
            description="\n\n".join(p for p in parts if p) or None,
            employment_type=req.get("JobSchedule") or req.get("ContractType"),
            remote_hint=(req.get("WorkplaceType") or req.get("WorkplaceTypeCode") or ""),
            published_at=parse_dt(req.get("PostedDate")),
            deadline=parse_dt(req.get("PostingEndDate")),
            department=req.get("JobFamily") or req.get("Department"),
            seniority_hint=req.get("ManagerLevel") or req.get("JobLevel"),
            raw={"site": site, "job_function": req.get("JobFunction"),
                 "study_level": req.get("StudyLevel"), "secondary": secondary},
        )

    async def _enrich(self, job: RawJob, host: str, site: str) -> None:
        url = (
            f"{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
            f'?expand=all&onlyData=true&finder=ById;Id="{job.source_job_id}",siteNumber={site}'
        )
        try:
            data = await self._get_json(url)
        except Exception:  # noqa: BLE001 - un detalle faltante no rompe la fuente
            return
        items = data.get("items") or []
        if items:
            job.description = html_to_text(items[0].get("ExternalDescriptionStr"))

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


class EightfoldSource(BaseJobSource):
    """Eightfold.ai — usado por BCG, Microsoft y varias consultoras.

    Se configura con `ats_token` (el subdominio) y `careers_url` con el dominio
    corporativo, por ejemplo token `bcg` y dominio `bcg.com`.

    Algunas empresas sirven la misma API desde su propio dominio en vez de
    `*.eightfold.ai` (Mercado Libre: `careers-meli.mercadolibre.com/api/positions`).
    Para esos casos se pasa `base_url` y se usa esa ruta.
    """

    key = "eightfold"
    label = "Eightfold"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "API pública /api/apply/v2/jobs que consume la propia career page. Sin auth."
    requires_config = True

    PAGE_SIZE = 50

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        params = target.params
        token = params.get("token") or ""
        base_url = (params.get("base_url") or "").rstrip("/")
        domain = params.get("domain") or (f"{token}.com" if token else "")
        location = params.get("location", "Argentina")
        company = params.get("company") or token or base_url

        if base_url:
            endpoint = f"{base_url}/api/positions"
            query = {"location": location, "country": location}
        else:
            endpoint = f"https://{token}.eightfold.ai/api/apply/v2/jobs"
            query = {"domain": domain, "location": location, "sort_by": "timestamp"}

        out: list[RawJob] = []
        start = 0
        while start <= params.get("max_offset", 300):
            data = await self._get_json(
                endpoint, params={**query, "start": start, "num": self.PAGE_SIZE},
            )
            positions = data.get("positions") or []
            for position in positions:
                out.append(self._to_raw(position, token, company, base_url))
            if len(positions) < self.PAGE_SIZE or not data.get("hasMore", True):
                break
            start += self.PAGE_SIZE
        return out

    def _to_raw(self, position: dict, token: str, company: str,
                base_url: str = "") -> RawJob:
        job_id = str(position.get("id"))
        locations = position.get("locations") or position.get("standardizedLocations") or []
        if isinstance(locations, str):
            locations = [locations]
        if base_url:
            url = f"{base_url}/es/positions?id={job_id}"
        else:
            url = (position.get("canonicalPositionUrl")
                   or f"https://{token}.eightfold.ai/careers/job/{job_id}")
        description = html_to_text(position.get("job_description"))
        posted = position.get("postedTs") or position.get("creationTs")
        return RawJob(
            source=self.key,
            source_job_id=f"{token or 'own'}:{job_id}",
            url=url,
            apply_url=url,
            title=position.get("name") or position.get("posting_name", ""),
            company=company,
            location=position.get("location") or ", ".join(str(x) for x in locations) or None,
            description=description or None,
            employment_type=position.get("type"),
            remote_hint=(position.get("work_location_option")
                         or position.get("workLocationOption")
                         or position.get("location_flexibility") or ""),
            published_at=parse_dt(position.get("t_create") or position.get("t_update")
                                  or posted),
            department=position.get("department") or position.get("business_unit"),
            seniority_hint=position.get("seniority") or position.get("type"),
            # Esta API no siempre devuelve la descripción: el análisis lo sabe.
            raw={"token": token, "needs_detail": not description,
                 "ats_job_id": position.get("ats_job_id") or position.get("atsJobId"),
                 "display_job_id": position.get("display_job_id") or position.get("displayJobId")},
        )

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


class AmazonJobsSource(BaseJobSource):
    """amazon.jobs — endpoint JSON público que usa su propio buscador.

    Cubre Amazon y AWS, que no están en ningún ATS de terceros.
    """

    key = "amazon_jobs"
    label = "Amazon Jobs"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "Endpoint público search.json que consume el propio buscador de amazon.jobs."

    BASE = "https://www.amazon.jobs/search.json"
    PAGE_SIZE = 100

    def default_targets(self) -> list[SourceTarget]:
        return [SourceTarget("ar", "Amazon · Argentina", {"country": "ARG", "company": "Amazon"})]

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        params = target.params
        company = params.get("company", "Amazon")
        out: list[RawJob] = []
        offset = 0
        while offset <= params.get("max_offset", 200):
            data = await self._get_json(
                self.BASE,
                params={"normalized_country_code[]": params.get("country", "ARG"),
                        "result_limit": self.PAGE_SIZE, "offset": offset,
                        "sort": "recent"},
            )
            jobs = data.get("jobs") or []
            for j in jobs:
                path = j.get("job_path") or ""
                url = f"https://www.amazon.jobs{path}"
                description = "\n\n".join(
                    html_to_text(j.get(field)) for field in
                    ("description", "basic_qualifications", "preferred_qualifications")
                    if j.get(field)
                )
                out.append(RawJob(
                    source=self.key,
                    source_job_id=str(j.get("id_icims") or j.get("id") or path),
                    url=url, apply_url=url,
                    title=j.get("title", ""),
                    company=j.get("company_name") or company,
                    location=j.get("location") or ", ".join(
                        x for x in (j.get("city"), j.get("state"), j.get("country_code")) if x
                    ) or None,
                    description=description or None,
                    employment_type=j.get("job_schedule_type"),
                    published_at=parse_dt(j.get("posted_date") or j.get("updated_time")),
                    department=j.get("business_category") or j.get("job_category"),
                    seniority_hint=j.get("job_level"),
                    raw={"team": j.get("team", {}).get("label") if isinstance(j.get("team"), dict) else None},
                ))
            if len(jobs) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


class PhenomSource(BaseJobSource):
    """Phenom People — el career site de muchas multinacionales.

    Aon, PepsiCo, Schneider Electric, AXA y varias más publican sobre esta
    plataforma. Expone `/api/jobs` en el propio dominio de carreras de la
    empresa, con descripción completa y ubicación estructurada.

    Se configura con `careers_url` = el host (ej. `jobs.aon.com`).
    """

    key = "phenom"
    label = "Phenom"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "API pública /api/jobs que consume la propia career page. Sin auth."
    requires_config = True

    PAGE_SIZE = 50

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        params = target.params
        host = (params.get("host") or "").replace("https://", "").replace("http://", "").strip("/")
        if not host:
            return []
        location = params.get("location", "Argentina")
        company = params.get("company") or host

        out: list[RawJob] = []
        offset = 0
        while offset <= params.get("max_offset", 200):
            data = await self._get_json(
                f"https://{host}/api/jobs",
                params={"location": location, "limit": self.PAGE_SIZE, "offset": offset},
            )
            jobs = data.get("jobs") or []
            for envoltorio in jobs:
                nodo = envoltorio.get("data", envoltorio)
                raw = self._to_raw(nodo, host, company)
                if raw is not None:
                    out.append(raw)
            if len(jobs) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE
        return out

    def _to_raw(self, nodo: dict, host: str, company: str) -> RawJob | None:
        titulo = nodo.get("title")
        if not titulo:
            return None
        job_id = str(nodo.get("slug") or nodo.get("req_id") or nodo.get("jobId") or titulo)
        # El filtro de la API es laxo: se confirma el país antes de ingerir.
        pais = str(nodo.get("country") or "")
        ubicacion = (nodo.get("full_location") or nodo.get("short_location")
                     or ", ".join(x for x in (nodo.get("city"), nodo.get("state"), pais) if x))
        url = (nodo.get("applyUrl") or nodo.get("apply_url")
               or f"https://{host}/job/{job_id}")
        categorias = nodo.get("categories") or []
        if isinstance(categorias, list) and categorias and isinstance(categorias[0], dict):
            departamento = ", ".join(c.get("name", "") for c in categorias if c.get("name"))
        else:
            departamento = ", ".join(str(c) for c in categorias) if categorias else None

        return RawJob(
            source=self.key,
            source_job_id=f"{host}:{job_id}",
            url=url, apply_url=url,
            title=titulo,
            company=nodo.get("hiring_organization") or company,
            location=ubicacion or None,
            description=html_to_text(nodo.get("description")),
            employment_type=nodo.get("employment_type"),
            remote_hint=str(nodo.get("work_type") or nodo.get("tags4") or ""),
            published_at=parse_dt(nodo.get("posted_date") or nodo.get("create_date")),
            deadline=parse_dt(nodo.get("posting_expiry_date")),
            department=departamento or None,
            seniority_hint=nodo.get("job_level") or nodo.get("career_level"),
            raw={"host": host, "req_id": nodo.get("req_id"), "ats_code": nodo.get("ats_code")},
        )

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw
