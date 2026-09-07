"""Agregadores con API pública y gratuita (§8 nivel 1-2).

Aportan cobertura de posiciones remotas que aceptan LATAM/Argentina y, en el
caso de Arbeitnow, del mercado de habla alemana (§26).
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


class RemotiveSource(BaseJobSource):
    key = "remotive"
    label = "Remotive"
    kind = SourceKind.AGGREGATOR
    compliance = ComplianceLevel.OFFICIAL_API
    compliance_note = "API pública documentada de Remotive (remotive.com/api/remote-jobs)."

    BASE = "https://remotive.com/api/remote-jobs"

    def default_targets(self) -> list[SourceTarget]:
        return [
            SourceTarget("business", "Remotive · business", {"category": "business"}),
            SourceTarget("product", "Remotive · product", {"category": "product"}),
            SourceTarget("marketing", "Remotive · marketing", {"category": "marketing"}),
            SourceTarget("data", "Remotive · data", {"category": "data"}),
            SourceTarget("finance", "Remotive · finance", {"category": "finance-legal"}),
            SourceTarget("customer", "Remotive · customer support", {"category": "customer-support"}),
        ]

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        params = {"limit": 100}
        if target.params.get("category"):
            params["category"] = target.params["category"]
        data = await self._get_json(self.BASE, params=params)
        out: list[RawJob] = []
        for j in data.get("jobs", []):
            out.append(
                RawJob(
                    source=self.key,
                    source_job_id=str(j.get("id")),
                    url=j.get("url", ""),
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    location=j.get("candidate_required_location") or "Remote",
                    description=html_to_text(j.get("description")),
                    employment_type=j.get("job_type"),
                    remote_hint="remote",
                    published_at=parse_dt(j.get("publication_date")),
                    salary_currency=None,
                    department=j.get("category"),
                    raw={"salary_text": j.get("salary"), "tags": j.get("tags")},
                )
            )
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


class ArbeitnowSource(BaseJobSource):
    key = "arbeitnow"
    label = "Arbeitnow (DACH)"
    kind = SourceKind.AGGREGATOR
    compliance = ComplianceLevel.OFFICIAL_API
    compliance_note = "API pública de Arbeitnow. Mercado alemán: sólo se ingieren avisos remotos."

    BASE = "https://www.arbeitnow.com/api/job-board-api"

    def default_targets(self) -> list[SourceTarget]:
        return [SourceTarget("all", "Arbeitnow · remoto DACH", {"pages": 3})]

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        out: list[RawJob] = []
        for page in range(1, int(target.params.get("pages", 2)) + 1):
            data = await self._get_json(self.BASE, params={"page": page})
            rows = data.get("data") or []
            if not rows:
                break
            for j in rows:
                # Sólo remoto: un aviso presencial en Alemania no sirve desde Buenos Aires.
                if not j.get("remote"):
                    continue
                out.append(
                    RawJob(
                        source=self.key,
                        source_job_id=str(j.get("slug")),
                        url=j.get("url", ""),
                        title=j.get("title", ""),
                        company=j.get("company_name", ""),
                        location=j.get("location") or "Remote (DACH)",
                        description=html_to_text(j.get("description")),
                        employment_type=", ".join(j.get("job_types") or []),
                        remote_hint="remote",
                        published_at=parse_dt(j.get("created_at")),
                        raw={"tags": j.get("tags"), "visa": j.get("visa_sponsorship")},
                    )
                )
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


class JobicySource(BaseJobSource):
    key = "jobicy"
    label = "Jobicy"
    kind = SourceKind.AGGREGATOR
    compliance = ComplianceLevel.OFFICIAL_API
    compliance_note = "API pública v2 de Jobicy para empleos remotos."

    BASE = "https://jobicy.com/api/v2/remote-jobs"

    def default_targets(self) -> list[SourceTarget]:
        return [
            SourceTarget("business", "Jobicy · business", {"industry": "business"}),
            SourceTarget("marketing", "Jobicy · marketing", {"industry": "marketing"}),
            SourceTarget("data", "Jobicy · data", {"industry": "data-science"}),
            SourceTarget("supporting", "Jobicy · customer success", {"industry": "supporting"}),
        ]

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        params = {"count": 50}
        if target.params.get("industry"):
            params["industry"] = target.params["industry"]
        data = await self._get_json(self.BASE, params=params)
        out: list[RawJob] = []
        for j in data.get("jobs", []):
            out.append(
                RawJob(
                    source=self.key,
                    source_job_id=str(j.get("id")),
                    url=j.get("url", ""),
                    title=j.get("jobTitle", ""),
                    company=j.get("companyName", ""),
                    location=j.get("jobGeo") or "Remote",
                    description=html_to_text(j.get("jobDescription") or j.get("jobExcerpt")),
                    employment_type=", ".join(j.get("jobType") or []),
                    remote_hint="remote",
                    published_at=parse_dt(j.get("pubDate")),
                    salary_min=j.get("annualSalaryMin"),
                    salary_max=j.get("annualSalaryMax"),
                    salary_currency=j.get("salaryCurrency"),
                    department=", ".join(j.get("jobIndustry") or []),
                    seniority_hint=", ".join(j.get("jobLevel") or [])
                    if isinstance(j.get("jobLevel"), list) else j.get("jobLevel"),
                    raw={"level": j.get("jobLevel")},
                )
            )
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


class HimalayasSource(BaseJobSource):
    key = "himalayas"
    label = "Himalayas"
    kind = SourceKind.AGGREGATOR
    compliance = ComplianceLevel.OFFICIAL_API
    compliance_note = "API pública de Himalayas para empleos remotos."

    BASE = "https://himalayas.app/jobs/api"

    def default_targets(self) -> list[SourceTarget]:
        return [SourceTarget("all", "Himalayas · remoto", {"limit": 100})]

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        data = await self._get_json(self.BASE, params={"limit": target.params.get("limit", 50)})
        out: list[RawJob] = []
        for j in data.get("jobs", []):
            locations = j.get("locationRestrictions") or []
            out.append(
                RawJob(
                    source=self.key,
                    source_job_id=str(j.get("guid") or j.get("id")),
                    url=j.get("applicationLink") or j.get("url", ""),
                    title=j.get("title", ""),
                    company=j.get("companyName", ""),
                    location=", ".join(locations) or "Remote",
                    description=html_to_text(j.get("description") or j.get("excerpt")),
                    employment_type=j.get("employmentType"),
                    remote_hint="remote",
                    published_at=parse_dt(j.get("pubDate")),
                    salary_min=j.get("minSalary"),
                    salary_max=j.get("maxSalary"),
                    salary_currency=j.get("salaryCurrency"),
                    seniority_hint=j.get("seniority"),
                    raw={"seniority": j.get("seniority"), "categories": j.get("categories")},
                )
            )
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw
