"""Workday CXS: endpoint JSON público que usan las propias career pages.

Sin autenticación, sin bypass de protecciones. Cada empresa se configura con
tenant / site / host (ej: santander / SantanderCareers / wd3).
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


class WorkdaySource(BaseJobSource):
    key = "workday"
    label = "Workday"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = (
        "Endpoint JSON público (/wday/cxs/) que la propia career page consume. Sin auth."
    )
    requires_config = True

    PAGE_SIZE = 20

    def _base(self, p: dict) -> str:
        host = p.get("host", "wd3")
        return f"https://{p['tenant']}.{host}.myworkdayjobs.com/wday/cxs/{p['tenant']}/{p['site']}"

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        p = target.params
        base = self._base(p)
        company = p.get("company") or p["tenant"]
        search_text = p.get("search_text", "")
        facets = p.get("applied_facets", {})
        out: list[RawJob] = []
        offset = 0
        while offset <= p.get("max_offset", 60):
            payload = {
                "appliedFacets": facets,
                "limit": self.PAGE_SIZE,
                "offset": offset,
                "searchText": search_text,
            }
            resp = await self.client.post(f"{base}/jobs", json=payload)
            resp.raise_for_status()
            data = resp.json()
            postings = data.get("jobPostings") or []
            for j in postings:
                path = j.get("externalPath") or ""
                url = f"https://{p['tenant']}.{p.get('host','wd3')}.myworkdayjobs.com/{p['site']}{path}"
                out.append(
                    RawJob(
                        source=self.key,
                        source_job_id=str(j.get("bulletFields", [path])[0] or path),
                        url=url,
                        apply_url=url,
                        title=j.get("title", ""),
                        company=company,
                        location=j.get("locationsText"),
                        description=None,
                        published_at=parse_dt(j.get("startDate")),
                        raw={"external_path": path, "posted_on": j.get("postedOn"),
                             "tenant": p["tenant"], "site": p["site"], "host": p.get("host", "wd3")},
                    )
                )
            if len(postings) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE

        for job in out:
            await self._enrich(job, base)
        return out

    async def _enrich(self, job: RawJob, base: str) -> None:
        path = job.raw.get("external_path")
        if not path:
            return
        try:
            data = await self._get_json(f"{base}{path}")
        except Exception:  # noqa: BLE001 - detalle opcional
            return
        info = data.get("jobPostingInfo") or {}
        job.description = html_to_text(info.get("jobDescription"))
        job.employment_type = info.get("timeType")
        job.published_at = parse_dt(info.get("startDate")) or job.published_at
        job.deadline = parse_dt(info.get("endDate"))
        if info.get("remoteType"):
            job.remote_hint = str(info["remoteType"])
        if info.get("externalUrl"):
            job.apply_url = info["externalUrl"]

        # El listado de Workday casi nunca trae `locationsText`; la ubicación real
        # (y el país) sólo aparecen en el detalle. Sin esto el filtro geográfico
        # descarta avisos argentinos por no tener ubicación declarada.
        country = ((info.get("country") or {}).get("descriptor")
                   or ((info.get("jobRequisitionLocation") or {}).get("country") or {}).get("descriptor"))
        primary = (info.get("location")
                   or (info.get("jobRequisitionLocation") or {}).get("descriptor"))
        extra = [str(x) for x in (info.get("additionalLocations") or []) if x]
        parts = [p for p in ([primary] + extra) if p]
        location = ", ".join(dict.fromkeys(parts))
        if country and country.lower() not in location.lower():
            location = f"{location}, {country}" if location else country
        if location:
            job.location = location

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw
