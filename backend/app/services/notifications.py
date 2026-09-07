"""Resumen diario y despacho por canal (§31).

Sólo se notifican oportunidades que superan el umbral: nunca se envían empleos
irrelevantes.
"""
from __future__ import annotations

import logging
import platform
import shutil
import smtplib
import subprocess
from email.message import EmailMessage

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Job, JobAnalysis, JobState, JobStatus, Notification, Recommendation, utcnow
from app.services.profile import get_preference, get_user

logger = logging.getLogger(__name__)

TOP_N = 3

# strftime("%B") depende del locale del sistema y devolvía "September" en un
# resumen escrito en español.
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_larga(fecha) -> str:
    return f"{fecha.day} de {MESES[fecha.month - 1]} de {fecha.year}"
DIGEST_RECOMMENDATIONS = {
    Recommendation.APPLY_NOW.value,
    Recommendation.STRONG.value,
    Recommendation.WORTH_IT.value,
}


def _emoji(analysis: JobAnalysis) -> str:
    if analysis.recommendation == Recommendation.APPLY_NOW.value:
        return "🔥"
    if analysis.german_advantage_score >= 70:
        return "🇩🇪"
    if analysis.recommendation == Recommendation.STRONG.value:
        return "⭐"
    return "🎓"


def build_daily_digest(db: Session, run_id: int | None = None) -> dict | None:
    """Arma el resumen con los empleos nuevos y relevantes de hoy."""
    user = get_user(db)
    threshold = float(get_preference(db, "display").get("min_display_score", 70.0))
    today = utcnow().date()

    rows = db.execute(
        select(Job, JobAnalysis, JobState)
        .join(JobAnalysis, JobAnalysis.job_id == Job.id)
        .join(JobState, (JobState.job_id == Job.id) & (JobState.user_id == user.id))
        .where(
            JobState.status == JobStatus.NEW.value,
            JobAnalysis.final_score >= threshold,
            JobAnalysis.eligible.is_(True),
            Job.is_duplicate.is_(False),
        )
        .order_by(JobAnalysis.final_score.desc())
    ).all()
    rows = [r for r in rows if r[0].first_seen_date.date() == today] or rows[:0]
    if not rows:
        return None

    top = rows[:TOP_N]
    lines = [
        f"Nuevos empleos para vos — {fecha_larga(today)}",
        "",
        f"{len(rows)} nuevas oportunidades relevantes.",
        "",
        f"🔥 TOP {len(top)}",
    ]
    for i, (job, analysis, _) in enumerate(top, start=1):
        lines.append(
            f"{i}. {job.job_title} — {job.company}\n"
            f"   Score {analysis.final_score:.0f}% · {analysis.summary or ''}\n"
            f"   {job.apply_url or job.url}"
        )
    lines += ["", "VER TODOS: http://localhost:3000/"]

    return {
        "subject": f"{len(rows)} nuevas oportunidades — {today.strftime('%d/%m')}",
        "body": "\n".join(lines),
        "count": len(rows),
        "top": [
            {
                "emoji": _emoji(a),
                "score": a.final_score,
                "title": j.job_title,
                "company": j.company,
                "url": j.apply_url or j.url,
            }
            for j, a, _ in top
        ],
    }


def dispatch(db: Session, digest: dict, run_id: int | None = None) -> list[Notification]:
    user = get_user(db)
    sent: list[Notification] = []

    channels: list[tuple[str, bool]] = [
        ("desktop", settings.notify_desktop_enabled and _desktop_available()),
        ("email", settings.notify_email_enabled),
        ("telegram", settings.notify_telegram_enabled),
    ]
    for channel, enabled in channels:
        note = Notification(
            user_id=user.id, run_id=run_id, channel=channel,
            subject=digest["subject"], body=digest["body"],
            status="pending" if enabled else "skipped",
        )
        db.add(note)
        db.flush()
        if not enabled:
            continue
        try:
            if channel == "desktop":
                _send_desktop(digest)
            elif channel == "email":
                _send_email(digest["subject"], digest["body"])
            elif channel == "telegram":
                _send_telegram(digest["body"])
            note.status = "sent"
            note.sent_at = utcnow()
        except Exception as exc:  # noqa: BLE001 - una notificación fallida no rompe la corrida
            logger.warning("notificación %s falló: %s", channel, exc)
            note.status = "error"
            note.error = str(exc)[:500]
        sent.append(note)

    # Siempre queda registrada la notificación in-app
    inapp = Notification(user_id=user.id, run_id=run_id, channel="in_app",
                         subject=digest["subject"], body=digest["body"],
                         status="sent", sent_at=utcnow())
    db.add(inapp)
    sent.append(inapp)
    return sent


def _desktop_available() -> bool:
    return platform.system() == "Darwin" and shutil.which("osascript") is not None


def _applescript_quote(value: str) -> str:
    """AppleScript no tiene escapes: se arma la cadena de forma literal y segura."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _send_desktop(digest: dict) -> None:
    """Notificación nativa de macOS. Sin cuentas, sin servicios, sin costo."""
    if not _desktop_available():
        raise RuntimeError("las notificaciones de escritorio requieren macOS")

    count = digest.get("count", 0)
    top = (digest.get("top") or [{}])[0]
    title = f"{count} oportunidad{'es' if count != 1 else ''} nueva{'s' if count != 1 else ''}"
    if top.get("title"):
        subtitle = f"{top['emoji']} {round(top['score'])}% · {top['title']}"[:100]
        body = f"{top.get('company', '')} — abrí Job Hunter para ver todas"[:120]
    else:
        subtitle = "Job Hunter"
        body = "Abrí la app para verlas"

    script = (
        f'display notification "{_applescript_quote(body)}" '
        f'with title "{_applescript_quote(title)}" '
        f'subtitle "{_applescript_quote(subtitle)}" '
        f'sound name "{_applescript_quote(settings.notify_desktop_sound)}"'
    )
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "osascript falló").strip()[:200])


def _send_email(subject: str, body: str) -> None:
    if not (settings.smtp_host and settings.notify_email_to):
        raise RuntimeError("SMTP no configurado")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user or "jobhunter@localhost"
    msg["To"] = settings.notify_email_to
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def _send_telegram(body: str) -> None:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        raise RuntimeError("Telegram no configurado")
    resp = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={"chat_id": settings.telegram_chat_id, "text": body,
              "disable_web_page_preview": True},
        timeout=20,
    )
    resp.raise_for_status()
