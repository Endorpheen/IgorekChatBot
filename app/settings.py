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

    mcp_feature_enabled: bool = False
    mcp_secret_key: Optional[str] = None
    mcp_stdio_enable: bool = False
    mcp_allow_internal: bool = False
    mcp_default_timeout_s: int = 30
    mcp_max_output_kb: int = 256
    mcp_max_calls_per_minute_per_thread: int = 10
    mcp_db_path: Path = Field(default=Path("data/mcp.sqlite"))
    mcp_log_path: Path = Field(default=Path("logs/mcp.log"))
    mcp_concurrency_limit: int = 3

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
            "http://localhost",
            "http://localhost:5173",
            "http://127.0.0.1",
            "http://127.0.0.1:5173",
            "https://igorek.end0databox.duckdns.org",
        ]
    )
    allow_origin_regex: str = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    webui_dir: Path = Field(default=Path("/app/web-ui"))

    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "openai/gpt-4o-mini"
    max_completion_tokens: int = 4096

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
