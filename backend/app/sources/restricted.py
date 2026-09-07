"""Fuentes con restricciones de uso automatizado (§8).

LinkedIn, Indeed, Bumeran, ZonaJobs y Glassdoor prohíben el scraping
automatizado en sus términos y/o lo bloquean activamente. NO se implementa
evasión de ninguna protección.

Cada adaptador queda:
  * deshabilitado por defecto,
  * con la vía legítima documentada (API oficial / feed / alerta),
  * capaz de operar si la usuaria configura una credencial de partner válida.

Además, `SavedSearchLinksSource` genera los enlaces de búsqueda ya armados para
esos portales, que es la alternativa permitida: la usuaria abre el link y ve
sus resultados en el sitio, sin que la app extraiga contenido.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from app.sources.base import (
    BaseJobSource,
    ComplianceLevel,
    RawJob,
    SourceKind,
    SourceTarget,
)


class _RestrictedSource(BaseJobSource):
    kind = SourceKind.BOARD
    compliance = ComplianceLevel.RESTRICTED
    enabled_by_default = False
    requires_config = True
    alternative = ""

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        if not self.config.get("api_credentials"):
            # Sin acuerdo/credencial oficial no se consulta la fuente.
            return []
        raise NotImplementedError(
            f"{self.key}: conectar aquí la API oficial con las credenciales provistas."
        )

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw

    async def health_check(self) -> tuple[bool, str]:
        if not self.config.get("api_credentials"):
            return True, f"deshabilitada por política del sitio · alternativa: {self.alternative}"
        return True, "credenciales configuradas"


class LinkedInSource(_RestrictedSource):
    key = "linkedin"
    label = "LinkedIn Jobs"
    compliance_note = (
        "El scraping automatizado viola los Términos de LinkedIn. Vía legítima: "
        "LinkedIn Talent Solutions / Job Posting API con acuerdo de partner."
    )
    alternative = "alerta de empleo de LinkedIn leída por IMAP (fuente email_alerts)"


class IndeedSource(_RestrictedSource):
    key = "indeed"
    label = "Indeed Argentina"
    compliance_note = (
        "Indeed discontinuó su API pública de búsqueda y bloquea scraping. "
        "Vía legítima: Indeed Publisher/Employer API con acuerdo."
    )
    alternative = "alerta por email de Indeed leída por IMAP (fuente email_alerts)"


class BumeranSource(_RestrictedSource):
    key = "bumeran"
    label = "Bumeran"
    compliance_note = (
        "Portal del grupo Jobint; sus términos no permiten extracción automatizada. "
        "Vía legítima: acuerdo comercial / feed de partners."
    )
    alternative = "alerta por email de Bumeran leída por IMAP (fuente email_alerts)"


class ZonaJobsSource(_RestrictedSource):
    key = "zonajobs"
    label = "ZonaJobs"
    compliance_note = "Mismo grupo y mismos términos que Bumeran."
    alternative = "alerta por email de ZonaJobs leída por IMAP (fuente email_alerts)"


class GlassdoorSource(_RestrictedSource):
    key = "glassdoor"
    label = "Glassdoor"
    compliance_note = "Términos restrictivos y protección anti-bot. Vía legítima: API de partner."
    alternative = "consulta manual para reputación de empresa"


class SavedSearchLinksSource(BaseJobSource):
    """No ingiere avisos: arma los links de búsqueda para portales restringidos.

    Es la alternativa permitida del §8: la app prepara la consulta, la usuaria
    la abre en el sitio original.
    """

    key = "saved_search_links"
    label = "Búsquedas guardadas (portales restringidos)"
    kind = SourceKind.BOARD
    compliance = ComplianceLevel.OFFICIAL_API
    compliance_note = "Sólo construye URLs de búsqueda públicas; no extrae contenido."

    TEMPLATES = {
        "linkedin": "https://www.linkedin.com/jobs/search/?keywords={q}&location={loc}&f_E=1%2C2&sortBy=DD",
        "indeed": "https://ar.indeed.com/jobs?q={q}&l={loc}&sort=date&explvl=entry_level",
        "bumeran": "https://www.bumeran.com.ar/empleos-busqueda-{qslug}.html",
        "zonajobs": "https://www.zonajobs.com.ar/empleos-busqueda-{qslug}.html",
        "glassdoor": "https://www.glassdoor.com.ar/Empleo/buenos-aires-{qslug}-empleos-SRCH_IL.0,12_IC3121459_KO13,{n}.htm",
        "google": "https://www.google.com/search?q={q}+empleo+{loc}&ibp=htl;jobs",
    }

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        return []

    def normalize_job(self, raw: RawJob) -> RawJob:
        return raw

    @classmethod
    def build_links(cls, queries: list[str], location: str = "Buenos Aires, Argentina") -> list[dict]:
        links: list[dict] = []
        for q in queries:
            qslug = q.lower().replace(" ", "-")
            for portal, tpl in cls.TEMPLATES.items():
                try:
                    url = tpl.format(q=quote_plus(q), loc=quote_plus(location), qslug=quote_plus(qslug),
                                     n=13 + len(qslug))
                except (KeyError, IndexError):
                    continue
                links.append({"portal": portal, "query": q, "url": url})
        return links
