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
    gmail_max_pages: int = 5
    gmail_max_messages: int = 100

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
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
    )
