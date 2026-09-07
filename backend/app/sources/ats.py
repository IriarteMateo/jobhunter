"""Adaptadores para APIs públicas de ATS (§8 nivel 3: public_ats_api).

Todos usan endpoints públicos y documentados de los job boards, sin
autenticación, sin evadir protecciones y respetando un rate limit conservador.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from app.sources.base import (
    BaseJobSource,
    ComplianceLevel,
    RawJob,
    SourceKind,
    SourceTarget,
)


BLOCK_TAGS = ("p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4",
              "h5", "h6", "section", "article", "table", "blockquote")


def html_to_text(html: str | None) -> str:
    """HTML -> texto plano conservando la estructura de líneas.

    Los saltos importan: el extractor de skills recorre el aviso línea por línea
    para separar "Requisitos" de "Deseable". Las etiquetas inline (<b>, <em>, <a>)
    NO deben cortar la línea.
    """
    if not html:
        return ""
    if "<" not in html:
        return html.strip()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    text = soup.get_text("")
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, OSError):
            return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
class GreenhouseSource(BaseJobSource):
    key = "greenhouse"
    label = "Greenhouse"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "API pública de job boards de Greenhouse (boards-api.greenhouse.io), sin auth."

    BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        token = target.params["token"]
        data = await self._get_json(self.BASE.format(token=token))
        company = target.params.get("company") or token
        out: list[RawJob] = []
        for j in data.get("jobs", []):
            loc = (j.get("location") or {}).get("name")
            offices = ", ".join(o.get("name", "") for o in (j.get("offices") or []) if o.get("name"))
            out.append(
                RawJob(
                    source=self.key,
                    source_job_id=str(j.get("id")),
                    url=j.get("absolute_url", ""),
                    apply_url=j.get("absolute_url"),
                    title=j.get("title", ""),
                    company=j.get("company_name") or company,
                    location=loc or offices or None,
                    description=html_to_text(j.get("content")),
                    published_at=parse_dt(j.get("first_published") or j.get("updated_at")),
                    deadline=parse_dt(j.get("application_deadline")),
                    department=", ".join(d.get("name", "") for d in (j.get("departments") or [])),
                    raw={"board": token, "offices": offices},
                )
            )
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        # Greenhouse escapa el HTML dentro de `content`.
        if raw.description and "&lt;" in raw.description:
            import html as _html

            raw.description = html_to_text(_html.unescape(raw.description))
        return raw


# --------------------------------------------------------------------------- #
class LeverSource(BaseJobSource):
    key = "lever"
    label = "Lever"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "API pública de postings de Lever (api.lever.co/v0/postings), sin auth."

    BASE = "https://api.lever.co/v0/postings/{token}?mode=json"

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        token = target.params["token"]
        data = await self._get_json(self.BASE.format(token=token))
        if not isinstance(data, list):
            return []
        company = target.params.get("company") or token
        out: list[RawJob] = []
        for j in data:
            cat = j.get("categories") or {}
            desc = html_to_text(j.get("descriptionPlain") or j.get("description"))
            lists = j.get("lists") or []
            for block in lists:
                desc += "\n\n" + html_to_text(block.get("text", "")) + "\n" + html_to_text(block.get("content", ""))
            desc += "\n\n" + html_to_text(j.get("additionalPlain") or j.get("additional") or "")
            out.append(
                RawJob(
                    source=self.key,
                    source_job_id=str(j.get("id")),
                    url=j.get("hostedUrl") or j.get("applyUrl", ""),
                    apply_url=j.get("applyUrl") or j.get("hostedUrl"),
                    title=j.get("text", ""),
                    company=company,
                    location=cat.get("location"),
                    description=desc.strip(),
                    employment_type=cat.get("commitment"),
                    remote_hint=(j.get("workplaceType") or ""),
                    published_at=parse_dt(j.get("createdAt")),
                    department=cat.get("team") or cat.get("department"),
                    raw={"board": token},
                )
            )
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


# --------------------------------------------------------------------------- #
class AshbySource(BaseJobSource):
    key = "ashby"
    label = "Ashby"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "API pública de job boards de Ashby (posting-api/job-board), sin auth."

    BASE = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        token = target.params["token"]
        data = await self._get_json(self.BASE.format(token=token))
        company = data.get("name") or target.params.get("company") or token
        out: list[RawJob] = []
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            secondary = ", ".join(j.get("secondaryLocations") and
                                  [s.get("location", "") for s in j["secondaryLocations"]] or [])
            comp = j.get("compensation") or {}
            summary = (comp.get("compensationTierSummary") or "") if isinstance(comp, dict) else ""
            out.append(
                RawJob(
                    source=self.key,
                    source_job_id=str(j.get("id")),
                    url=j.get("jobUrl", ""),
                    apply_url=j.get("applyUrl") or j.get("jobUrl"),
                    title=j.get("title", ""),
                    company=company,
                    location=j.get("location") or secondary or None,
                    description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                    employment_type=j.get("employmentType"),
                    remote_hint=("remote" if j.get("isRemote") else (j.get("workplaceType") or "")),
                    published_at=parse_dt(j.get("publishedAt")),
                    department=j.get("department") or j.get("team"),
                    seniority_hint=j.get("employmentType"),
                    raw={"board": token, "compensation_summary": summary, "secondary": secondary},
                )
            )
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


# --------------------------------------------------------------------------- #
class SmartRecruitersSource(BaseJobSource):
    key = "smartrecruiters"
    label = "SmartRecruiters"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "API pública Posting API de SmartRecruiters, sin auth. Filtra por país."

    LIST = "https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100&offset={offset}&country={country}"
    DETAIL = "https://api.smartrecruiters.com/v1/companies/{token}/postings/{pid}"

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        token = target.params["token"]
        country = target.params.get("country", "ar")
        company = target.params.get("company") or token
        out: list[RawJob] = []
        offset = 0
        while True:
            data = await self._get_json(self.LIST.format(token=token, offset=offset, country=country))
            content = data.get("content") or []
            for p in content:
                loc = p.get("location") or {}
                loc_str = ", ".join(
                    x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x
                )
                out.append(
                    RawJob(
                        source=self.key,
                        source_job_id=str(p.get("id")),
                        url=f"https://jobs.smartrecruiters.com/{token}/{p.get('id')}",
                        title=p.get("name", ""),
                        company=(p.get("company") or {}).get("name") or company,
                        location=loc_str or None,
                        remote_hint="remote" if loc.get("remote") else "",
                        employment_type=(p.get("typeOfEmployment") or {}).get("label"),
                        published_at=parse_dt(p.get("releasedDate")),
                        department=(p.get("department") or {}).get("label"),
                        seniority_hint=(p.get("experienceLevel") or {}).get("label"),
                        raw={"board": token, "experience_level": (p.get("experienceLevel") or {}).get("label")},
                    )
                )
            if len(content) < 100 or offset > 400:
                break
            offset += 100
        # La descripción sólo viene en el detalle: la traemos para los que quedan.
        for job in out:
            try:
                d = await self._get_json(self.DETAIL.format(token=token, pid=job.source_job_id))
            except Exception:  # noqa: BLE001 - una descripción faltante no rompe la fuente
                continue
            job.apply_url = d.get("applyUrl") or d.get("postingUrl") or job.url
            job.url = d.get("postingUrl") or job.url
            sections = ((d.get("jobAd") or {}).get("sections") or {})
            parts = []
            for name in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
                sec = sections.get(name) or {}
                if sec.get("text"):
                    parts.append(html_to_text(sec["text"]))
            job.description = "\n\n".join(parts).strip() or None
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


# --------------------------------------------------------------------------- #
class WorkableSource(BaseJobSource):
    key = "workable"
    label = "Workable"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "Endpoint público del widget de Workable (apply.workable.com/api/v1/widget)."

    LIST = "https://apply.workable.com/api/v1/widget/accounts/{token}?details=true"

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        token = target.params["token"]
        data = await self._get_json(self.LIST.format(token=token))
        company = (data.get("name") or target.params.get("company") or token)
        out: list[RawJob] = []
        for j in data.get("jobs", []):
            loc = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
            out.append(
                RawJob(
                    source=self.key,
                    source_job_id=str(j.get("shortcode") or j.get("id")),
                    url=j.get("url", ""),
                    apply_url=j.get("application_url") or j.get("url"),
                    title=j.get("title", ""),
                    company=company,
                    location=loc or None,
                    description=html_to_text(j.get("description")) + "\n\n" + html_to_text(j.get("requirements")),
                    employment_type=j.get("employment_type"),
                    remote_hint="remote" if j.get("telecommuting") else "",
                    published_at=parse_dt(j.get("published_on")),
                    department=j.get("department"),
                    raw={"board": token},
                )
            )
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


# --------------------------------------------------------------------------- #
class RecruiteeSource(BaseJobSource):
    key = "recruitee"
    label = "Recruitee"
    kind = SourceKind.ATS
    compliance = ComplianceLevel.PUBLIC_ATS_API
    compliance_note = "API pública de ofertas de Recruitee ({token}.recruitee.com/api/offers)."

    LIST = "https://{token}.recruitee.com/api/offers/"

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        token = target.params["token"]
        data = await self._get_json(self.LIST.format(token=token))
        company = target.params.get("company") or token
        out: list[RawJob] = []
        for j in data.get("offers", []):
            loc = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
            out.append(
                RawJob(
                    source=self.key,
                    source_job_id=str(j.get("id")),
                    url=j.get("careers_url") or j.get("url", ""),
                    apply_url=j.get("careers_apply_url") or j.get("careers_url"),
                    title=j.get("title", ""),
                    company=company,
                    location=loc or j.get("location"),
                    description=html_to_text(j.get("description")) + "\n\n" + html_to_text(j.get("requirements")),
                    employment_type=j.get("employment_type_code"),
                    remote_hint=j.get("remote") and "remote" or "",
                    published_at=parse_dt(j.get("published_at")),
                    department=j.get("department"),
                    raw={"board": token},
                )
            )
        return out

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw
