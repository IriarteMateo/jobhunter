"""Career pages que arman su listado con JavaScript (§8, nivel HTML público).

Algunas empresas grandes —Deloitte, Google, Disney, McKinsey— publican sus
avisos en páginas cuyo HTML llega vacío: el contenido lo genera el navegador.
Un lector de HTML común ve 190 KB sin una sola fila.

Esta fuente abre la página con un navegador real (Playwright), espera a que
termine de cargar y extrae los avisos de dos maneras complementarias:

  1. **Capturando las respuestas JSON** que la propia página pide por detrás.
     Es lo mejor que puede pasar: datos estructurados, sin adivinar HTML.
  2. Leyendo el DOM ya renderizado (datos schema.org/JobPosting si están, o
     selectores CSS configurados por sitio).

No evade nada: renderiza una página pública igual que cualquier persona con un
navegador, verifica robots.txt antes de entrar y respeta el rate limit. Queda
apagada salvo `ENABLE_BROWSER_RENDERING=true`.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

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

# Sustrings de URL cuyas respuestas JSON vale la pena capturar
DEFAULT_CAPTURE_HINTS = (
    "job", "search", "position", "requisition", "vacan", "opening", "career",
)


@dataclass
class RenderedSite:
    """Cómo leer una career page concreta."""

    key: str
    company: str
    url: str                                   # admite {location}
    wait_selector: str | None = None
    capture_hints: tuple[str, ...] = DEFAULT_CAPTURE_HINTS
    parser: str = "auto"                       # nombre en PARSERS
    link_pattern: str | None = None            # regex de href de aviso
    max_pages: int = 1
    page_param: str | None = None


def _text(node: Any, *keys: str) -> str | None:
    for key in keys:
        value = node.get(key) if isinstance(node, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for inner in ("name", "label", "descriptor", "text", "title"):
                if isinstance(value.get(inner), str) and value[inner].strip():
                    return value[inner].strip()
    return None


def _walk(payload: Any):
    """Recorre un JSON arbitrario devolviendo los dicts que parecen un aviso."""
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            keys = {k.lower() for k in node}
            has_title = bool(keys & {"title", "name", "jobtitle", "postingname",
                                     "job_title", "positionname"})
            has_id = bool(keys & {"id", "jobid", "job_id", "requisitionid", "slug",
                                  "externalpath", "jobseqno", "displayjobid"})
            if has_title and has_id:
                yield node
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))


def parse_generic_json(payloads: list[Any], site: RenderedSite,
                       base_url: str) -> list[RawJob]:
    """Extrae avisos de cualquier JSON capturado, sin conocer su forma."""
    out: dict[str, RawJob] = {}
    for payload in payloads:
        for node in _walk(payload):
            title = _text(node, "title", "name", "jobTitle", "postingName",
                          "job_title", "positionName")
            if not title or len(title) < 3:
                continue
            job_id = str(
                _text(node, "id", "jobId", "job_id", "requisitionId", "slug",
                      "externalPath", "jobSeqNo", "displayJobId") or title
            )
            if job_id in out:
                continue
            url = _text(node, "url", "jobUrl", "applyUrl", "canonicalPositionUrl",
                        "externalPath", "link", "jobPostingUrl") or base_url
            if url.startswith("/"):
                from urllib.parse import urljoin

                url = urljoin(base_url, url)
            location = _text(node, "location", "locationsText", "primaryLocation",
                             "city", "jobLocation", "locationName")
            description = _text(node, "description", "jobDescription",
                                "descriptionPlain", "summary", "shortDescription")
            out[job_id] = RawJob(
                source="rendered_careers",
                source_job_id=f"{site.key}:{job_id}",
                url=url, apply_url=url,
                title=title, company=site.company,
                location=location,
                description=html_to_text(description) if description else None,
                published_at=parse_dt(_text(node, "postedDate", "datePosted",
                                            "publishedAt", "postedOn", "createdAt")),
                seniority_hint=_text(node, "level", "seniority", "experienceLevel"),
                raw={"site": site.key, "rendered": True},
            )
    return list(out.values())


PARSERS: dict[str, Callable[[list[Any], RenderedSite, str], list[RawJob]]] = {
    "auto": parse_generic_json,
}


class RenderedCareerSource(BaseJobSource):
    key = "rendered_careers"
    label = "Career pages con JavaScript (navegador)"
    kind = SourceKind.CAREERS
    compliance = ComplianceLevel.PUBLIC_HTML
    compliance_note = (
        "Renderiza páginas públicas con un navegador real y captura sus propias "
        "respuestas JSON. Verifica robots.txt. Apagada salvo ENABLE_BROWSER_RENDERING=true."
    )
    enabled_by_default = False
    requires_config = True

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        if not settings.enable_browser_rendering:
            return []
        site = target.params.get("site")
        if site is None:
            site = RenderedSite(
                key=target.key, company=target.params.get("company", target.label),
                url=target.params["url"],
                wait_selector=target.params.get("wait_selector"),
                parser=target.params.get("parser", "auto"),
                link_pattern=target.params.get("link_pattern"),
            )
        url = site.url.format(location=target.params.get("location", "Argentina"))
        if not await is_allowed(url):
            raise RuntimeError(f"robots.txt no permite {url}")
        return await self._render_and_extract(site, url)

    async def _render_and_extract(self, site: RenderedSite, url: str) -> list[RawJob]:
        from playwright.async_api import async_playwright

        payloads: list[Any] = []
        dom_jobs: list[RawJob] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=settings.http_user_agent,
                    locale="es-AR",
                    viewport={"width": 1440, "height": 1000},
                )
                page = await context.new_page()

                async def on_response(response):
                    target_url = response.url.lower()
                    if not any(h in target_url for h in site.capture_hints):
                        return
                    ctype = (response.headers or {}).get("content-type", "")
                    if "json" not in ctype:
                        return
                    try:
                        payloads.append(await response.json())
                    except Exception:  # noqa: BLE001 - respuesta no parseable
                        return

                page.on("response", on_response)
                await page.goto(url, timeout=settings.browser_timeout_seconds * 1000,
                                wait_until="domcontentloaded")
                if site.wait_selector:
                    try:
                        await page.wait_for_selector(
                            site.wait_selector, timeout=settings.browser_wait_ms * 2
                        )
                    except Exception:  # noqa: BLE001 - seguimos con lo que haya
                        pass
                await page.wait_for_timeout(settings.browser_wait_ms)

                dom_jobs = await self._from_dom(page, site, url)
            finally:
                await browser.close()

        parser = PARSERS.get(site.parser, parse_generic_json)
        json_jobs = parser(payloads, site, url)

        # Se prefiere el JSON (estructurado); el DOM completa lo que falte.
        seen = {j.source_job_id for j in json_jobs}
        merged = json_jobs + [j for j in dom_jobs if j.source_job_id not in seen]
        logger.info("rendered %s: %s desde JSON, %s desde DOM -> %s",
                    site.key, len(json_jobs), len(dom_jobs), len(merged))
        return merged

    async def _from_dom(self, page, site: RenderedSite, base_url: str) -> list[RawJob]:
        """Datos estructurados del DOM, o links de aviso si no hay."""
        jobs: list[RawJob] = []

        # 1) schema.org/JobPosting incrustado
        try:
            blocks = await page.eval_on_selector_all(
                'script[type="application/ld+json"]', "els => els.map(e => e.textContent)"
            )
        except Exception:  # noqa: BLE001
            blocks = []
        from app.sources.careers import CompanyCareerSource

        reader = CompanyCareerSource()
        for block in blocks or []:
            try:
                payload = json.loads(block or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            for node in reader._iter_job_postings(payload):
                raw = reader._node_to_raw(node, base_url, site.company)
                raw.source = self.key
                raw.source_job_id = f"{site.key}:{raw.source_job_id}"
                jobs.append(raw)
        if jobs:
            return jobs

        # 2) Links que parezcan un aviso, con su texto visible
        pattern = site.link_pattern or r"/(?:job|jobs|trabajo|empleo|position|vacante)s?/"
        try:
            rows = await page.eval_on_selector_all(
                "a[href]",
                """els => els.map(e => ({
                    href: e.href,
                    text: (e.innerText || e.textContent || '').trim().slice(0, 220)
                }))""",
            )
        except Exception:  # noqa: BLE001
            rows = []
        regex = re.compile(pattern, re.I)
        seen: set[str] = set()
        for row in rows or []:
            href = row.get("href") or ""
            text = " ".join((row.get("text") or "").split())
            if not regex.search(href) or len(text) < 6 or href in seen:
                continue
            seen.add(href)
            lines = [x.strip() for x in (row.get("text") or "").splitlines() if x.strip()]
            title = lines[0] if lines else text[:120]
            location = next((x for x in lines[1:] if len(x) < 90), None)
            jobs.append(RawJob(
                source=self.key,
                source_job_id=f"{site.key}:{href.rsplit('/', 1)[-1][:80]}",
                url=href, apply_url=href, title=title[:220],
                company=site.company, location=location,
                raw={"site": site.key, "rendered": True, "from": "dom"},
            ))
        return jobs

    def normalize_job(self, raw: RawJob) -> RawJob:
        raw.title = re.sub(r"\s+", " ", raw.title).strip()
        return raw

    async def health_check(self) -> tuple[bool, str]:
        if not settings.enable_browser_rendering:
            return True, "apagada · activá ENABLE_BROWSER_RENDERING=true"
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                await browser.close()
            return True, "navegador disponible"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"
