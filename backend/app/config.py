"""Configuración central. Todo lo sensible viene de variables de entorno."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "AI Job Hunter"
    environment: str = "development"
    timezone: str = "America/Argentina/Buenos_Aires"
    log_level: str = "INFO"

    # --- Base de datos ---
    # SQLite por defecto para levantar sin dependencias externas.
    # En producción: postgresql+psycopg://user:pass@host:5432/jobhunter
    database_url: str = f"sqlite:///{BASE_DIR / 'jobhunter.db'}"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- IA ---
    # "heuristic" funciona sin API key. "anthropic" / "openai" requieren key.
    ai_provider: str = "heuristic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    ai_max_jobs_per_run: int = 120       # tope duro de llamadas LLM por corrida
    ai_prefilter_threshold: float = 45.0  # score determinístico mínimo para gastar LLM
    ai_timeout_seconds: int = 60

    # --- Scheduler ---
    scheduler_enabled: bool = True
    daily_run_hour: int = 7
    daily_run_minute: int = 30

    # --- Ingesta ---
    http_timeout_seconds: int = 25
    http_max_concurrency: int = 8
    http_user_agent: str = (
        "AIJobHunter/1.0 (personal job search assistant; +contact via app owner)"
    )
    source_rate_limit_seconds: float = 0.4
    enable_html_scraping: bool = False   # fuentes HTML públicas, off por defecto

    # --- Renderizado con navegador (Playwright) ---
    # Necesario para career pages que arman el listado con JavaScript
    # (Deloitte, Google, Disney, McKinsey). Sigue respetando robots.txt.
    enable_browser_rendering: bool = False
    browser_timeout_seconds: int = 45
    browser_wait_ms: int = 3500
    browser_max_pages: int = 3

    # --- Producto ---
    min_display_score: float = 70.0

    # --- Alertas por email (IMAP) ---
    # Vía legítima para portales que no permiten scraping: la usuaria crea una
    # alerta de búsqueda en el portal y la app lee esos mails de su casilla.
    imap_enabled: bool = False
    imap_host: str | None = None
    imap_port: int = 993
    imap_user: str | None = None
    imap_password: str | None = None
    imap_folder: str = "INBOX"
    imap_lookback_days: int = 3
    imap_max_messages: int = 60

    # --- Notificaciones ---
    notify_email_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    notify_email_to: str | None = None
    # Notificación nativa de macOS: no requiere cuenta, servicio ni configuración.
    notify_desktop_enabled: bool = True
    notify_desktop_sound: str = "Glass"

    notify_telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
