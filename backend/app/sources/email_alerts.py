"""Ingesta de alertas de empleo por email (§8, alternativa permitida).

LinkedIn, Indeed, Bumeran, ZonaJobs y Glassdoor no permiten extracción
automatizada de sus sitios. Pero **todos** ofrecen alertas de búsqueda por mail:
la usuaria configura la alerta en el portal y el portal le envía las ofertas a
su propia casilla.

Leer el correo propio no es scraping: es el canal que el sitio eligió para
entregar esos datos. Esta fuente conecta por IMAP a la casilla de la usuaria,
busca los mails de alerta de los últimos días y extrae los avisos.

Limitación honesta: el mail trae título, empresa, ubicación y link, pero NO la
descripción completa. Esos avisos quedan con `needs_detail=True`, reciben menor
confianza en el análisis y la tarjeta invita a abrir el link. Si el mismo puesto
aparece por el ATS oficial de la empresa, la deduplicación los fusiona y el
apply_url queda apuntando a la página oficial (§10).
"""
from __future__ import annotations

import email
import imaplib
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from email.header import decode_header, make_header
from email.message import Message
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from app.config import settings
from app.models import utcnow
from app.sources.ats import parse_dt
from app.sources.base import (
    BaseJobSource,
    ComplianceLevel,
    RawJob,
    SourceKind,
    SourceTarget,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertProvider:
    key: str
    label: str
    senders: tuple[str, ...]
    url_pattern: re.Pattern
    id_group: str | None = None      # nombre del grupo del regex con el id
    id_query_param: str | None = None  # o el parámetro de query que lo contiene
    tracking_params: tuple[str, ...] = ("trackingId", "refId", "trk", "eBP", "lipi")


PROVIDERS: dict[str, AlertProvider] = {
    "linkedin": AlertProvider(
        key="linkedin",
        label="LinkedIn",
        senders=("linkedin.com",),
        url_pattern=re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?P<id>\d+)", re.I),
        id_group="id",
    ),
    "indeed": AlertProvider(
        key="indeed",
        label="Indeed",
        senders=("indeed.com", "indeed.com.ar"),
        url_pattern=re.compile(r"indeed\.com(?:\.ar)?/(?:rc/clk|viewjob|pagead/clk)", re.I),
        id_query_param="jk",
    ),
    "bumeran": AlertProvider(
        key="bumeran",
        label="Bumeran",
        senders=("bumeran.com", "bumeran.com.ar"),
        url_pattern=re.compile(r"bumeran\.com\.ar/empleos/[^\"'\s]*?-(?P<id>\d+)\.html", re.I),
        id_group="id",
    ),
    "zonajobs": AlertProvider(
        key="zonajobs",
        label="ZonaJobs",
        senders=("zonajobs.com", "zonajobs.com.ar"),
        url_pattern=re.compile(r"zonajobs\.com\.ar/empleos/[^\"'\s]*?-(?P<id>\d+)\.html", re.I),
        id_group="id",
    ),
    "glassdoor": AlertProvider(
        key="glassdoor",
        label="Glassdoor",
        senders=("glassdoor.com", "glassdoor.com.ar"),
        url_pattern=re.compile(r"glassdoor\.com(?:\.ar)?/(?:job-listing|partner/jobListing)", re.I),
        id_query_param="jobListingId",
    ),
}

# Texto de navegación de los mails que nunca es un puesto
NOISE_TITLES = {
    "ver todos", "ver más", "ver mas", "see all jobs", "see all", "view job",
    "ver empleo", "postularme", "apply now", "unsubscribe", "darse de baja",
    "configurar alertas", "manage alerts", "ver todas las ofertas", "más empleos",
    "ayuda", "help", "privacidad", "privacy", "linkedin", "indeed", "bumeran",
    "zonajobs", "glassdoor", "ver oferta", "postulate", "postúlate",
}

LOCATION_HINTS = re.compile(
    r"(argentina|buenos aires|caba|capital federal|remoto|remote|h[ií]brido|"
    r"hybrid|presencial|on-?site|zona norte|san isidro|vicente l[oó]pez|"
    r"mart[ií]nez|olivos|palermo|belgrano|n[uú][ñn]ez|retiro|c[oó]rdoba|rosario)",
    re.I,
)
SEPARATORS = re.compile(r"\s*[·•|–—]\s*|\s{2,}|\n+")


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001 - encabezado mal formado
        return value


def _html_part(message: Message) -> str:
    """Devuelve el cuerpo HTML (o el texto plano si no hay HTML)."""
    html = ""
    plain = ""
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        if part.get_content_type() == "text/html":
            html += text
        elif part.get_content_type() == "text/plain":
            plain += text
    return html or plain


def clean_url(url: str, provider: AlertProvider) -> str:
    """Quita los parámetros de tracking para que el mismo aviso no se duplique."""
    url = unquote(url.strip())
    parsed = urlparse(url)
    if not parsed.query:
        return url.split("#")[0]
    kept = [
        f"{k}={v[0]}"
        for k, v in parse_qs(parsed.query).items()
        if k not in provider.tracking_params and v
    ]
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return f"{base}?{'&'.join(kept)}" if kept else base


def extract_job_id(url: str, provider: AlertProvider) -> str | None:
    match = provider.url_pattern.search(url)
    if not match:
        return None
    if provider.id_group:
        try:
            return match.group(provider.id_group)
        except IndexError:
            return None
    if provider.id_query_param:
        values = parse_qs(urlparse(url).query).get(provider.id_query_param)
        if values:
            return values[0]
    # Sin id explícito: la URL limpia identifica el aviso de forma estable
    return clean_url(url, provider).rsplit("/", 1)[-1] or None


def _context_lines(anchor, title: str) -> list[str]:
    """Texto alrededor del link, que es donde vienen empresa y ubicación."""
    node = anchor
    for _ in range(4):
        node = node.parent
        if node is None:
            break
        text = node.get_text("\n", strip=True)
        if len(text) > len(title) + 4:
            lines = [
                line.strip()
                for chunk in text.split("\n")
                for line in SEPARATORS.split(chunk)
                if line.strip()
            ]
            return [line for line in lines if line.lower() != title.lower()]
    return []


def parse_alert_html(html: str, provider: AlertProvider, received_at=None) -> list[RawJob]:
    """Extrae los avisos de un mail de alerta.

    Estrategia deliberadamente defensiva: cada portal cambia el HTML de sus
    mails sin avisar, así que se ancla en lo único estable —el link al aviso—
    y el resto se deduce del texto que lo rodea.
    """
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, RawJob] = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not provider.url_pattern.search(href):
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if not title or title.lower() in NOISE_TITLES or len(title) < 3:
            continue
        job_id = extract_job_id(href, provider)
        if not job_id:
            continue
        # El primer link de cada aviso suele ser el del título; los siguientes
        # ("Postularme") apuntan al mismo id y se descartan.
        if job_id in found:
            continue

        lines = _context_lines(anchor, title)
        company = ""
        location = ""
        for line in lines:
            if line.lower() in NOISE_TITLES or len(line) > 120:
                continue
            if not location and LOCATION_HINTS.search(line):
                location = line
            elif not company:
                company = line
            if company and location:
                break

        found[job_id] = RawJob(
            source="email_alerts",
            source_job_id=f"{provider.key}:{job_id}",
            url=clean_url(href, provider),
            apply_url=clean_url(href, provider),
            title=title,
            company=company or "Empresa no identificada",
            location=location or None,
            description=None,
            published_at=received_at,
            raw={"provider": provider.key, "needs_detail": True,
                 "via": "alerta de email", "context": lines[:4]},
        )
    return list(found.values())


class EmailAlertsSource(BaseJobSource):
    """Lee las alertas de empleo que los portales envían a la casilla propia."""

    key = "email_alerts"
    label = "Alertas por email (LinkedIn, Indeed, Bumeran…)"
    kind = SourceKind.BOARD
    compliance = ComplianceLevel.USER_INBOX
    compliance_note = (
        "No consulta los portales: lee por IMAP los mails de alerta que ellos mismos "
        "envían a la casilla de la usuaria. Requiere IMAP_ENABLED=true y credenciales propias."
    )
    enabled_by_default = False
    requires_config = True

    def default_targets(self) -> list[SourceTarget]:
        if not settings.imap_enabled:
            return []
        return [SourceTarget("inbox", "Alertas de empleo por email", {})]

    async def search_jobs(self, target: SourceTarget) -> list[RawJob]:
        if not settings.imap_enabled:
            return []
        missing = [
            name for name, value in (
                ("IMAP_HOST", settings.imap_host),
                ("IMAP_USER", settings.imap_user),
                ("IMAP_PASSWORD", settings.imap_password),
            ) if not value
        ]
        if missing:
            raise RuntimeError(f"faltan variables de entorno: {', '.join(missing)}")
        return self._read_inbox()

    def _read_inbox(self) -> list[RawJob]:
        since = (utcnow() - timedelta(days=settings.imap_lookback_days)).strftime("%d-%b-%Y")
        jobs: list[RawJob] = []

        with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as imap:
            imap.login(settings.imap_user, settings.imap_password)
            imap.select(settings.imap_folder, readonly=True)

            message_ids: list[bytes] = []
            for provider in PROVIDERS.values():
                for sender in provider.senders:
                    status, data = imap.search(None, f'(SINCE {since} FROM "{sender}")')
                    if status == "OK" and data and data[0]:
                        message_ids.extend(data[0].split())

            seen: set[bytes] = set()
            ordered = [m for m in reversed(message_ids) if not (m in seen or seen.add(m))]
            for message_id in ordered[: settings.imap_max_messages]:
                status, data = imap.fetch(message_id, "(RFC822)")
                if status != "OK" or not data or not isinstance(data[0], tuple):
                    continue
                try:
                    jobs.extend(self._parse_message(email.message_from_bytes(data[0][1])))
                except Exception as exc:  # noqa: BLE001 - un mail roto no corta la fuente
                    logger.warning("no se pudo leer un mail de alerta: %s", exc)
        logger.info("alertas por email: %s avisos extraídos", len(jobs))
        return jobs

    def _parse_message(self, message: Message) -> list[RawJob]:
        sender = _decode(message.get("From", "")).lower()
        provider = next(
            (p for p in PROVIDERS.values() if any(s in sender for s in p.senders)), None
        )
        if provider is None:
            return []
        html = _html_part(message)
        if not html:
            return []
        received = parse_dt(_decode(message.get("Date")))
        try:
            received = email.utils.parsedate_to_datetime(message.get("Date"))
            received = received.replace(tzinfo=None) if received.tzinfo else received
        except (TypeError, ValueError):
            pass
        jobs = parse_alert_html(html, provider, received)
        subject = _decode(message.get("Subject"))
        for job in jobs:
            job.raw["subject"] = subject[:200]
        return jobs

    def normalize_job(self, raw: RawJob) -> RawJob:
        raw.title = re.sub(r"\s+", " ", raw.title).strip()
        # "Empresa · Buenos Aires" a veces viene junto en el nombre de la empresa
        if raw.company and " · " in raw.company:
            company, _, rest = raw.company.partition(" · ")
            raw.company = company.strip()
            raw.location = raw.location or rest.strip()
        return raw

    async def health_check(self) -> tuple[bool, str]:
        if not settings.imap_enabled:
            return True, "deshabilitada · activá IMAP_ENABLED y cargá tus credenciales"
        try:
            with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as imap:
                imap.login(settings.imap_user, settings.imap_password)
                imap.select(settings.imap_folder, readonly=True)
            return True, f"conectado a {settings.imap_host}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"
