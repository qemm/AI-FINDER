"""
models.py — Pydantic request / response models for the AI-FINDER REST API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, HttpUrl


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    """Payload for POST /api/v1/scan."""

    urls: list[str] = []
    github_search: bool = False
    github_token: Optional[str] = None
    gitlab_search: bool = False
    gitlab_token: Optional[str] = None


class CrawlRequest(BaseModel):
    """Payload for POST /api/v1/crawl."""

    github_token: Optional[str] = None
    gitlab_token: Optional[str] = None
    target_url: Optional[str] = None
    use_github: bool = True
    use_gitlab: bool = True
    max_queries: Optional[int] = None
    urls_file: str = "urls.txt"


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class DorkItem(BaseModel):
    query: str
    description: str
    tags: list[str]
    platform: str


class StatsResponse(BaseModel):
    total: int
    with_secrets: int
    total_secret_findings: int
    by_platform: dict[str, int]


class SecretFinding(BaseModel):
    id: int
    file_id: int
    rule_name: Optional[str]
    line_number: Optional[int]
    redacted: Optional[str]
    context: Optional[str]


class FileResult(BaseModel):
    id: int
    url: str
    content_hash: str
    platform: str
    indexed_at: str
    tags: str
    has_secrets: int
    raw_content: Optional[str] = None


class FileDetail(FileResult):
    secret_findings: list[SecretFinding] = []


class PaginatedResults(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int
    results: list[FileResult]


class JobStatus(BaseModel):
    job_id: str
    status: str          # queued | running | done | error
    message: str = ""
    saved: int = 0
    total: int = 0
    error: Optional[str] = None


class SearchResult(BaseModel):
    url: str
    platform: str
    tags: str
    distance: float
    has_secrets: bool
    document_excerpt: str
