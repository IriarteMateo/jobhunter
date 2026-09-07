"""Fuentes que leen páginas de Careers públicas (§6, §48).

Nivel 4-5 de la escala de §8: sólo HTML público, respetando robots.txt y sólo
si `ENABLE_HTML_SCRAPING=true`. Prioriza datos estructurados schema.org/JobPosting,
que es el formato que las propias empresas publican para buscadores.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.config import settings
from app.sources.ats import html_to_text, parse_dt
from app.sources.base import (
    BaseJobSource,
    ComplianceLevel,
    RawJob,
    SourceKind,
    SourceTarget,
)
from app.sources.compliance import is_allowed

logger = logging.getLogger(__name__)


class RobotsDisallowed(RuntimeError):
    pass


class CompanyCareerSource(BaseJobSource):
    """Lector genérico de career pages vía JSON-LD (schema.org/JobPosting)."""

    key = "company_careers"
    label = "Career pages (JSON-LD)"
    kind = SourceKind.CAREERS
    compliance = ComplianceLevel.PUBLIC_HTML
    compliance_note = (
        "Lee sólo HTML público y datos estructurados schema.org/JobPosting. "
        "Verifica robots.txt antes de cada request. Desactivado salvo ENABLE_HTML_SCRAPING=true."
    )
    enabled_by_default = False
    requires_config = True

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        if not settings.enable_html_scraping:
            return []
        url = target.params["url"]
        if not await is_allowed(url):
            raise RobotsDisallowed(f"robots.txt no permite {url}")
        html = await self._get_text(url, headers={"Accept": "text/html"})
        company = target.params.get("company") or target.label
        return self._parse_jsonld(html, url, company)

    def _parse_jsonld(self, html: str, base_url: str, company: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "lxml")
        out: list[RawJob] = []
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(tag.string or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            for node in self._iter_job_postings(payload):
                out.append(self._node_to_raw(node, base_url, company))
        return [j for j in out if j.title]

    @staticmethod
    def _iter_job_postings(payload):
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                node_type = node.get("@type")
                types = node_type if isinstance(node_type, list) else [node_type]
                if "JobPosting" in types:
                    yield node
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)

    def _node_to_raw(self, node: dict, base_url: str, company: str) -> RawJob:
        org = node.get("hiringOrganization") or {}
        loc = node.get("jobLocation") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        addr = (loc or {}).get("address") or {}
        loc_str = ", ".join(
            str(x) for x in (addr.get("addressLocality"), addr.get("addressRegion"),
                             addr.get("addressCountry")) if x
        )
        salary = node.get("baseSalary") or {}
        value = salary.get("value") if isinstance(salary, dict) else {}
        value = value if isinstance(value, dict) else {}
        url = node.get("url") or base_url
        return RawJob(
            source=self.key,
            source_job_id=str(node.get("identifier") or node.get("url") or node.get("title")),
            url=urljoin(base_url, url),
            apply_url=urljoin(base_url, node.get("applicationUrl") or url),
            title=str(node.get("title") or ""),
            company=(org.get("name") if isinstance(org, dict) else None) or company,
            location=loc_str or (node.get("jobLocationType") and "Remote") or None,
            description=html_to_text(node.get("description")),
            employment_type=node.get("employmentType") if isinstance(node.get("employmentType"), str) else None,
            remote_hint="remote" if node.get("jobLocationType") == "TELECOMMUTE" else "",
            published_at=parse_dt(node.get("datePosted")),
            deadline=parse_dt(node.get("validThrough")),
            salary_min=_num(value.get("minValue")),
            salary_max=_num(value.get("maxValue")),
            salary_currency=salary.get("currency") if isinstance(salary, dict) else None,
            raw={"schema": "JobPosting"},
        )

    def normalize_job(self, raw: RawJob) -> RawJob:
        raw.title = re.sub(r"\s+", " ", raw.title).strip()
        return raw


class SuccessFactorsSource(BaseJobSource):
    """SAP SuccessFactors career sites (jobs.<empresa>.com/search)."""

    key = "successfactors"
    label = "SAP SuccessFactors"
    kind = SourceKind.CAREERS
    compliance = ComplianceLevel.PUBLIC_HTML
    compliance_note = (
        "Listado público de SuccessFactors. Verifica robots.txt antes de cada request "
        "y no lee nada si ENABLE_HTML_SCRAPING=false."
    )
    # Se habilita por defecto porque se auto-limita: sin ENABLE_HTML_SCRAPING no
    # hace ni un request, y ante un robots.txt que no lo permita se detiene.
    enabled_by_default = True
    requires_config = True

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        if not settings.enable_html_scraping:
            return []
        base = target.params["base_url"].rstrip("/")
        query = target.params.get("location", "Argentina")
        company = target.params.get("company") or target.label
        out: list[RawJob] = []
        for startrow in (0, 25):
            url = f"{base}/search/?q=&locationsearch={query}&startrow={startrow}"
            if not await is_allowed(url):
                raise RobotsDisallowed(f"robots.txt no permite {url}")
            html = await self._get_text(url, headers={"Accept": "text/html"})
            rows = self._parse_rows(html, base, company)
            out.extend(rows)
            if len(rows) < 25:
                break
        return out

    def _parse_rows(self, html: str, base: str, company: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "lxml")
        out: list[RawJob] = []
        for row in soup.select("tr.data-row"):
            link = row.select_one("a.jobTitle-link") or row.select_one("a")
            if not link:
                continue
            href = urljoin(base, link.get("href", ""))
            loc = row.select_one(".jobLocation")
            date = row.select_one(".jobDate")
            out.append(
                RawJob(
                    source=self.key,
                    source_job_id=href.rsplit("/", 2)[-2] if "/" in href else href,
                    url=href,
                    apply_url=href,
                    title=link.get_text(strip=True),
                    company=company,
                    location=loc.get_text(strip=True) if loc else None,
                    description=None,  # se completa con fetch_job
                    published_at=parse_dt(date.get_text(strip=True) if date else None),
                    raw={"needs_detail": True},
                )
            )
        return out

    async def fetch_job(self, raw: RawJob) -> RawJob:
        if raw.description or not settings.enable_html_scraping:
            return raw
        if not await is_allowed(raw.url):
            return raw
        try:
            html = await self._get_text(raw.url, headers={"Accept": "text/html"})
        except Exception:  # noqa: BLE001
            return raw
        soup = BeautifulSoup(html, "lxml")
        body = soup.select_one(".job") or soup.select_one("[itemprop=description]") or soup
        raw.description = html_to_text(str(body))
        return raw

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
