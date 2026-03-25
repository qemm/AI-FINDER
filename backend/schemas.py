from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class CrawlJobRequest(BaseModel):
    use_github: bool = True
    use_gitlab: bool = True
    use_web_search: bool = True
    engines: list[str] = ["duckduckgo", "bing", "google"]
    web_dork_sources: str = "all"
    target_url: Optional[str] = None
    max_queries: Optional[int] = None
    max_web_dorks: Optional[int] = 20
    depth: int = 2
    check_reachability: bool = True
    github_token: Optional[str] = None
    gitlab_token: Optional[str] = None


class ScanJobRequest(BaseModel):
    urls: list[str]


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued | running | done | error
    stats: dict = {}
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


class FileRecord(BaseModel):
    id: int
    url: str
    content_hash: str
    platform: str
    indexed_at: str
    tags: str
    has_secrets: int


class FileDetail(BaseModel):
    id: int
    url: str
    content_hash: str
    platform: str
    indexed_at: str
    tags: str
    has_secrets: int
    raw_content: Optional[str] = None
    secrets: list["SecretFinding"] = []


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


class SecretFinding(BaseModel):
    id: int
    file_id: int
    rule_name: str
    line_number: Optional[int]
    redacted: str
    context: str
    url: Optional[str] = None
    platform: Optional[str] = None
    indexed_at: Optional[str] = None


class SecretRuleStat(BaseModel):
    rule_name: str
    count: int


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class PlatformStat(BaseModel):
    platform: str
    count: int


class DashboardStats(BaseModel):
    total_files: int
    total_secrets: int
    files_with_secrets: int
    platforms: list[PlatformStat]
    secrets_by_rule: list[SecretRuleStat]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SemanticSearchResult(BaseModel):
    url: str
    platform: str
    tags: str
    score: float
    snippet: str
