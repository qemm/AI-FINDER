from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Data paths
    db_path: str = "/app/data/ai_finder.db"
    vector_db_path: str = "/app/data/vector_db"
    urls_file: str = "/app/data/urls.txt"
    export_path: str = "/app/data/export.json"

    # API tokens (optional)
    github_token: Optional[str] = None
    gitlab_token: Optional[str] = None

    # Logging — set LOG_LEVEL=DEBUG to see every HTTP request/dork/engine call
    log_level: str = "DEBUG"

    # Web search — official API keys avoid CAPTCHAs entirely.
    # Google Custom Search (100 free queries/day):
    #   https://developers.google.com/custom-search/v1/introduction
    google_cse_key: Optional[str] = None   # API key
    google_cse_id: Optional[str] = None    # Custom Search Engine ID ("cx")
    # Brave Search API (2 000 free queries/month):
    #   https://api.search.brave.com
    brave_search_key: Optional[str] = None
    # Optional HTTP/SOCKS5 proxy for scraping engines (helps with IP blocks).
    # Examples: http://user:pass@host:3128   socks5://host:1080
    https_proxy: Optional[str] = None

    # CORS — comma-separated list of allowed origins
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
