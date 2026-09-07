"""Detección automática del ATS de una empresa a partir de su página de carreras.

Es lo que hace que la lista de empresas objetivo escale: en vez de averiguar a
mano qué sistema usa cada compañía, se pega la URL de su sección de empleos y el
detector la identifica, arma la configuración del conector y **la verifica
consultando la API real** antes de proponerla.

No es scraping de avisos: se lee una única página pública para reconocer sobre
qué plataforma está construida, igual que haría una persona mirando el link al
que la redirige "Ver oportunidades".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.sources.base import SourceTarget
from app.sources.compliance import is_allowed

logger = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# (ats_type, patrón, cómo armar la config a partir de los grupos capturados)
FINGERPRINTS: list[tuple[str, re.Pattern]] = [
    ("greenhouse", re.compile(
        r"(?:job-)?boards\.greenhouse\.io/(?:embed/job_board\?for=)?(?P<token>[\w.-]+)", re.I)),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/(?P<token>[\w.-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/(?P<token>[\w.-]+)", re.I)),
    ("smartrecruiters", re.compile(
        r"(?:jobs|careers)\.smartrecruiters\.com/(?P<token>[\w.-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/(?P<token>[\w.-]+)", re.I)),
    ("recruitee", re.compile(r"(?P<token>[\w-]+)\.recruitee\.com", re.I)),
    ("workday", re.compile(
        r"(?P<tenant>[\w-]+)\.(?P<host>wd\d+)\.myworkdayjobs\.com/"
        # El segmento de idioma ("/es/", "/en-US/") no es el nombre del sitio
        r"(?:[a-z]{2}(?:-[A-Z]{2})?/)?(?P<site>[\w-]+)", re.I)),
    ("oracle_recruiting", re.compile(
        r"(?P<host>https://[\w.-]+\.fa\.[\w\d-]+\.oraclecloud\.com)"
        r"/hcmUI/CandidateExperience(?:/[\w-]+)?/sites/(?P<site>[\w-]+)", re.I)),
    ("eightfold", re.compile(r"(?P<token>[\w-]+)\.eightfold\.ai", re.I)),
    ("phenom", re.compile(
        r"(?:phenompeople|ph-cdn\.com|phenom\.com)", re.I)),
    ("successfactors", re.compile(
        r"(?P<host>https?://[\w.-]+)/(?:search|go)/\?[^\"']*?(?:locationsearch|q)=", re.I)),
]

# Plataformas que reconocemos pero para las que todavía no hay conector.
# Se informan igual: es más útil saber que existe a que aparezca "desconocido".
UNSUPPORTED = {
    "avature": re.compile(r"(?P<token>[\w-]+)\.avature\.net", re.I),
    "taleo": re.compile(r"(?P<token>[\w-]+)\.taleo\.net", re.I),
    "icims": re.compile(r"(?P<token>[\w-]+)\.icims\.com", re.I),
    "brassring": re.compile(r"(?:[\w-]+\.brassring\.com|krb-sjobs)", re.I),
}

SUPPORTED_LABEL = {
    "greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby",
    "smartrecruiters": "SmartRecruiters", "workable": "Workable",
    "recruitee": "Recruitee", "workday": "Workday",
    "oracle_recruiting": "Oracle Recruiting Cloud", "eightfold": "Eightfold",
    "successfactors": "SAP SuccessFactors", "phenom": "Phenom",
}


@dataclass
class Detection:
    detected: bool = False
    supported: bool = False
    ats_type: str | None = None
    ats_label: str | None = None
    ats_token: str | None = None
    careers_url: str | None = None      # config del conector (host|site, dominio, etc.)
    final_url: str | None = None
    verified: bool = False
    jobs_found: int | None = None
    sample_titles: list[str] = field(default_factory=list)
    message: str = ""
    evidence: str | None = None

    def as_dict(self) -> dict:
        return {
            "detected": self.detected, "supported": self.supported,
            "ats_type": self.ats_type, "ats_label": self.ats_label,
            "ats_token": self.ats_token, "careers_url": self.careers_url,
            "final_url": self.final_url, "verified": self.verified,
            "jobs_found": self.jobs_found, "sample_titles": self.sample_titles,
            "message": self.message, "evidence": self.evidence,
        }


async def _load_page(url: str) -> tuple[str, str]:
    """Devuelve (url_final, contenido). Respeta robots.txt.

    Muchas career pages responden 403 a un cliente HTTP simple, o arman el
    listado con JavaScript. Si eso pasa y el renderizado está habilitado, se
    reintenta con un navegador real —que es lo mismo que ve cualquier persona—
    manteniendo la verificación de robots.txt.
    """
    if not await is_allowed(url):
        raise PermissionError("el robots.txt del sitio no permite leer esa página")
    try:
        async with httpx.AsyncClient(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": BROWSER_UA}, follow_redirects=True,
        ) as client:
            response = await client.get(url)
        response.raise_for_status()
        return str(response.url), response.text[:500_000]
    except Exception as exc:  # noqa: BLE001
        rendered = await _load_page_rendered(url)
        if rendered is None:
            raise exc
        return rendered


async def _load_page_rendered(url: str) -> tuple[str, str] | None:
    """Abre la página con un navegador real. None si no está disponible."""
    if not settings.enable_browser_rendering:
        return None
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--disable-http2"])
            try:
                context = await browser.new_context(
                    user_agent=BROWSER_UA, locale="es-AR",
                    viewport={"width": 1440, "height": 1000},
                )
                page = await context.new_page()
                await page.goto(url, timeout=settings.browser_timeout_seconds * 1000,
                                wait_until="domcontentloaded")
                await page.wait_for_timeout(settings.browser_wait_ms)
                return str(page.url), (await page.content())[:500_000]
            finally:
                await browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("render de %s falló: %s", url, exc)
        return None


def fingerprint(blob: str) -> tuple[str, dict] | None:
    for ats_type, pattern in FINGERPRINTS:
        match = pattern.search(blob)
        if match:
            return ats_type, {k: v for k, v in match.groupdict().items() if v}
    return None


def fingerprint_unsupported(blob: str) -> tuple[str, dict] | None:
    for name, pattern in UNSUPPORTED.items():
        match = pattern.search(blob)
        if match:
            return name, {k: v for k, v in (match.groupdict() or {}).items() if v}
    return None


def build_config(ats_type: str, groups: dict, final_url: str) -> tuple[str | None, str | None]:
    """Devuelve (ats_token, careers_url) tal como los espera el registry."""
    if ats_type == "workday":
        return (groups.get("tenant"),
                f"{groups.get('tenant')}|{groups.get('site')}|{groups.get('host', 'wd3')}")
    if ats_type == "oracle_recruiting":
        return None, f"{groups.get('host')}|{groups.get('site', 'CX_1')}"
    if ats_type == "eightfold":
        token = groups.get("token")
        # El dominio corporativo suele ser <token>.com; se corrige a mano si no.
        return token, f"{token}.com"
    if ats_type == "successfactors":
        return None, groups.get("host")
    if ats_type == "phenom":
        # El host de carreras es el propio dominio de la página detectada
        from urllib.parse import urlparse

        return None, urlparse(final_url).netloc
    return groups.get("token"), None


async def verify(ats_type: str, token: str | None, careers_url: str | None,
                 company: str) -> tuple[bool, int, list[str], str]:
    """Consulta la API detectada para confirmar que el conector realmente anda."""
    from app.sources.registry import get_source

    params: dict = {"company": company}
    if ats_type == "workday":
        cfg = (careers_url or "").split("|")
        if len(cfg) < 2:
            return False, 0, [], "falta tenant/site de Workday"
        params |= {"tenant": cfg[0], "site": cfg[1],
                   "host": cfg[2] if len(cfg) > 2 else "wd3", "search_text": "Argentina",
                   "max_offset": 0}
    elif ats_type == "oracle_recruiting":
        cfg = (careers_url or "").split("|")
        params |= {"host": cfg[0], "site": cfg[1] if len(cfg) > 1 else "CX_1",
                   "location": "Argentina", "max_offset": 0}
    elif ats_type == "eightfold":
        params |= {"token": token or "", "domain": careers_url or "",
                   "location": "Argentina", "max_offset": 0}
    elif ats_type == "successfactors":
        params |= {"base_url": careers_url or "", "location": "Argentina"}
    elif ats_type == "phenom":
        params |= {"host": careers_url or "", "location": "Argentina"}
    else:
        params |= {"token": token or ""}
        if ats_type == "smartrecruiters":
            params |= {"country": "ar"}

    source = get_source(ats_type)
    try:
        async with source:
            jobs = await source.search_jobs(SourceTarget(ats_type, company, params))
    except Exception as exc:  # noqa: BLE001
        return False, 0, [], f"{type(exc).__name__}: {str(exc)[:160]}"
    return True, len(jobs), [j.title for j in jobs[:5]], ""


async def detect(url: str, company: str = "", run_verification: bool = True) -> Detection:
    result = Detection()
    if not url or not url.startswith("http"):
        result.message = "Necesito la URL completa de la sección de empleos (https://…)."
        return result

    try:
        final_url, body = await _load_page(url)
    except PermissionError as exc:
        result.message = str(exc)
        return result
    except Exception as exc:  # noqa: BLE001
        result.message = f"No pude abrir esa página: {type(exc).__name__}"
        return result

    result.final_url = final_url
    blob = f"{final_url}\n{body}"

    hit = fingerprint(blob)
    # Si el HTML plano no dijo nada, el listado puede armarse con JavaScript:
    # se reintenta renderizando antes de darse por vencido.
    if hit is None and fingerprint_unsupported(blob) is None:
        rendered = await _load_page_rendered(url)
        if rendered is not None and rendered[1] != body:
            final_url, body = rendered
            result.final_url = final_url
            blob = f"{final_url}\n{body}"
            hit = fingerprint(blob)

    if hit is None:
        unsupported = fingerprint_unsupported(blob)
        if unsupported:
            name, _ = unsupported
            result.detected = True
            result.supported = False
            result.ats_type = name
            result.ats_label = name.title()
            result.message = (
                f"Usa {name.title()}, que todavía no tiene conector. "
                "Podés seguirla igual con una alerta por email o importando avisos a mano."
            )
            return result
        result.message = (
            "No reconocí el ATS. Suele pasar cuando la página arma el listado con "
            "JavaScript: probá con la URL del buscador de empleos, no la de la landing."
        )
        return result

    ats_type, groups = hit
    token, careers_url = build_config(ats_type, groups, final_url)
    result.detected = True
    result.supported = True
    result.ats_type = ats_type
    result.ats_label = SUPPORTED_LABEL.get(ats_type, ats_type)
    result.ats_token = token
    result.careers_url = careers_url
    result.evidence = (groups and ", ".join(f"{k}={v}" for k, v in groups.items())) or None

    if not run_verification:
        result.message = f"Detectado {result.ats_label}."
        return result

    ok, count, titles, error = await verify(ats_type, token, careers_url, company or url)
    result.verified = ok
    result.jobs_found = count if ok else None
    result.sample_titles = titles
    if not ok:
        result.message = (
            f"Detecté {result.ats_label}, pero la consulta de prueba falló ({error}). "
            "Revisá el token antes de guardar."
        )
    elif count:
        result.message = f"{result.ats_label} conectado: {count} búsquedas en Argentina."
    else:
        result.message = (
            f"{result.ats_label} conectado, pero hoy no tiene búsquedas abiertas en "
            "Argentina. Guardala igual: se revisa en cada corrida."
        )
    return result
