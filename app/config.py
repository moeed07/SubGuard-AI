"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    google_cloud_project: str
    app_base_url: str
    google_oauth_client_id: str
    google_oauth_client_secret: str
    session_secret: str
    token_encryption_key: str
    service_mode: str
    gemini_model: str
    google_api_key: str
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_email: str = ""
    smtp_app_password: str = ""
    gmail_max_pages: int = 5
    gmail_max_messages: int = 100

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_email and self.smtp_app_password)

    @property
    def is_production(self) -> bool:
        return self.app_base_url.startswith("https://")

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.app_base_url.rstrip('/')}/auth/google/callback"

    @property
    def oauth_configured(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT", "").strip(),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:8000").strip(),
        google_oauth_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip(),
        google_oauth_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip(),
        session_secret=os.getenv("SESSION_SECRET", "").strip(),
        token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY", "").strip(),
        service_mode=os.getenv("SERVICE_MODE", "web").strip().lower() or "web",
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip(),
        google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com",
        smtp_port=int(os.getenv("SMTP_PORT", "587").strip() or "587"),
        smtp_email=os.getenv("SMTP_EMAIL", "").strip(),
        smtp_app_password=os.getenv("SMTP_APP_PASSWORD", "").strip(),
    )
