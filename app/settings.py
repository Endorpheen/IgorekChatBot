from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = "DEBUG"
    max_image_upload_mb: int = 20
    upload_dir: str = "uploads"
    upload_dir_abs: Optional[Path] = None
    upload_url_prefix: str = "/uploads"
    upload_ttl_days: int = 7
    upload_max_total_mb: int = 1024
    upload_clean_interval_seconds: int = 3600

    google_api_key: Optional[str] = None
    google_cse_id: Optional[str] = None
    google_search_endpoint: str = "https://www.googleapis.com/customsearch/v1"
    google_search_max_results: int = 5
    google_search_rate_limit: int = 5
    google_search_rate_window: int = 60
    google_search_cache_ttl: int = 30

    browser_service_url: str = "http://browser:8000/browse"
    sandbox_service_url: str = "http://sandbox_executor:8000/execute"

    allow_origins: List[str] = Field(
        default_factory=lambda: [
            "https://igorekchatbot.ru",
            "https://igorek.end0databox.duckdns.org",
        ]
    )
    allow_localhost: bool = False  # Enable localhost for development only
    allow_origin_regex: str = r"^https://(igorekchatbot\.ru|igorek\.end0databox\.duckdns\.org)$"

    webui_dir: Path = Field(default=Path("/app/web-ui"))

    docs_auth_enabled: bool = True
    docs_auth_username: Optional[str] = None
    docs_auth_password: Optional[str] = None

    session_cookie_name: str = "igc_session"
    session_header_name: str = "X-Session-Token"
    session_secret: Optional[str] = None
    session_ttl_seconds: int = 7 * 24 * 60 * 60
    legacy_session_compat_enabled: bool = True
    legacy_session_allowed_origins: List[str] = Field(
        default_factory=lambda: [
            "https://igorekchatbot.ru",
            "https://igorek.end0databox.duckdns.org",
        ]
    )

    signed_link_secret: Optional[str] = None
    signed_link_ttl_seconds: int = 300
    signed_link_compat_enabled: bool = True

    rate_limit_chat_per_minute: int = 60
    rate_limit_image_analyze_per_minute: int = 15
    rate_limit_file_analyze_per_hour: int = 30
    rate_limit_image_generate_per_minute: int = 20
    rate_limit_mcp_per_minute: int = 30

    allowed_agentrouter_base_urls: List[str] = Field(default_factory=list)

    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "openai/gpt-4o-mini"
    max_completion_tokens: int = 4096

    @computed_field
    def effective_allow_origins(self) -> List[str]:
        origins = self.allow_origins.copy()
        if self.allow_localhost:
            origins.extend([
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                "http://localhost:3010",  # Backend port
                "http://127.0.0.1:3010",
            ])
        return origins

    @computed_field
    def effective_legacy_session_allowed_origins(self) -> List[str]:
        origins = self.legacy_session_allowed_origins.copy()
        if self.allow_localhost:
            origins.extend([
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                "http://localhost:3010",  # Backend port
                "http://127.0.0.1:3010",
            ])
        return origins

    @computed_field
    def max_image_upload_bytes(self) -> int:
        return self.max_image_upload_mb * 1024 * 1024

    @computed_field
    def upload_dir_path(self) -> Path:
        base = self.upload_dir_abs if self.upload_dir_abs is not None else Path.cwd() / self.upload_dir
        return Path(base).resolve()

    @computed_field
    def upload_max_total_bytes(self) -> int:
        return self.upload_max_total_mb * 1024 * 1024

    @computed_field
    def max_request_size(self) -> int:
        return self.max_image_upload_bytes + 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_upload_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
