"""Chequeo de robots.txt antes de leer HTML público (§8).

Se cachea por host durante la corrida. Si robots.txt no permite la ruta, la
fuente se marca `skipped` en vez de ignorar la política del sitio.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_cache: dict[str, RobotFileParser | None] = {}


async def _load(host_root: str) -> RobotFileParser | None:
    if host_root in _cache:
        return _cache[host_root]
    parser = RobotFileParser()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(f"{host_root}/robots.txt",
                                    headers={"User-Agent": settings.http_user_agent})
        if resp.status_code >= 400:
            parser = None  # sin robots.txt publicado -> se permite
        else:
            parser.parse(resp.text.splitlines())
    except Exception as exc:  # noqa: BLE001
        logger.debug("robots.txt no disponible para %s: %s", host_root, exc)
        parser = None
    _cache[host_root] = parser
    return parser


async def is_allowed(url: str, user_agent: str | None = None) -> bool:
    """True si robots.txt permite (o no existe) el acceso a `url`."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    root = f"{parsed.scheme}://{parsed.netloc}"
    parser = await _load(root)
    if parser is None:
        return True
    return parser.can_fetch(user_agent or settings.http_user_agent, url)


def reset_cache() -> None:
    _cache.clear()
