"""
main.py — FastAPI application for AI-FINDER.

Exposes the same discovery / extraction / classification pipeline that
``poc.py`` drives via the CLI, but through a REST API and a Shodan-inspired
web frontend.

Endpoints
---------
GET  /                          Serve the web frontend.
GET  /api/v1/stats              Aggregate database statistics.
GET  /api/v1/results            Paginated, filterable list of findings.
GET  /api/v1/results/{id}       Single finding with secret details.
GET  /api/v1/platforms          Distinct platform labels in the database.
GET  /api/v1/dorks              All generated search queries / dorks.
POST /api/v1/scan               Start an async scan job.
GET  /api/v1/jobs/{job_id}      Poll scan / crawl job status.
POST /api/v1/crawl              Start an async crawl job.
GET  /api/v1/search             Semantic search against the vector store.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ai_finder.discovery import (
    GitHubQueryGenerator,
    GitLabQueryGenerator,
    GoogleDorkGenerator,
    S3DorkGenerator,
)
from ai_finder.extractor import FileExtractor
from ai_finder.logger import configure_logging
from ai_finder.processor import FileProcessor
from ai_finder.scanner import SecretScanner
from ai_finder.storage import Storage
from ai_finder.vector_store import VectorStore
from ai_finder.crawler import Crawler

from api.models import (
    CrawlRequest,
    DorkItem,
    FileDetail,
    FileResult,
    JobStatus,
    PaginatedResults,
    ScanRequest,
    SearchResult,
    SecretFinding,
    StatsResponse,
)

# ---------------------------------------------------------------------------
# Initialise logging (INFO by default; override via LOG_LEVEL env var)
# ---------------------------------------------------------------------------

configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))

_log = logging.getLogger("ai_finder.api")

# ---------------------------------------------------------------------------
# Default paths (overridable via environment variables)
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get("DB_PATH", "ai_finder.db")
_VECTOR_DB_PATH = os.environ.get("VECTOR_DB_PATH", None)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI-FINDER",
    description=(
        "OSINT engine for discovering, extracting and classifying "
        "AI agent configuration files exposed in public repositories."
    ),
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# In-memory job registry  {job_id: JobStatus}
# ---------------------------------------------------------------------------

_jobs: dict[str, JobStatus] = {}

# ---------------------------------------------------------------------------
# Static files & frontend
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR / "static")),
    name="static",
)


@app.get("/", include_in_schema=False)
async def serve_frontend() -> FileResponse:
    return FileResponse(str(_FRONTEND_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Helper — shared Storage instance per request
# ---------------------------------------------------------------------------


def _storage() -> Storage:
    return Storage(_DB_PATH)


# ---------------------------------------------------------------------------
# GET /api/v1/stats
# ---------------------------------------------------------------------------


@app.get("/api/v1/stats", response_model=StatsResponse, tags=["results"])
def get_stats() -> StatsResponse:
    """Return aggregate statistics about the stored AI-config findings."""
    data = _storage().stats()
    return StatsResponse(**data)


# ---------------------------------------------------------------------------
# GET /api/v1/platforms
# ---------------------------------------------------------------------------


@app.get("/api/v1/platforms", response_model=list[str], tags=["results"])
def get_platforms() -> list[str]:
    """Return the distinct platform labels present in the database."""
    return _storage().list_platforms()


# ---------------------------------------------------------------------------
# GET /api/v1/results
# ---------------------------------------------------------------------------


@app.get("/api/v1/results", response_model=PaginatedResults, tags=["results"])
def list_results(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
    platform: Optional[str] = Query(None, description="Filter by platform label"),
    has_secrets: Optional[bool] = Query(None, description="Filter by secrets flag"),
    q: Optional[str] = Query(None, description="Full-text search (URL / tags / content)"),
) -> PaginatedResults:
    """Return a paginated, optionally filtered list of discovered AI config files."""
    storage = _storage()
    offset = (page - 1) * per_page
    rows = storage.list_filtered(
        platform=platform,
        has_secrets=has_secrets,
        search=q,
        limit=per_page,
        offset=offset,
    )
    total = storage.count_filtered(platform=platform, has_secrets=has_secrets, search=q)
    pages = max(1, math.ceil(total / per_page))
    results = [
        FileResult(
            id=r["id"],
            url=r["url"],
            content_hash=r["content_hash"],
            platform=r["platform"],
            indexed_at=r["indexed_at"],
            tags=r["tags"],
            has_secrets=r["has_secrets"],
        )
        for r in rows
    ]
    return PaginatedResults(
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        results=results,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/results/{id}
# ---------------------------------------------------------------------------


@app.get("/api/v1/results/{result_id}", response_model=FileDetail, tags=["results"])
def get_result(result_id: int) -> FileDetail:
    """Return a single finding including its secret findings and raw content."""
    storage = _storage()
    row = storage.get_by_id(result_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Result not found")
    findings = [
        SecretFinding(**f) for f in storage.get_secret_findings(result_id)
    ]
    return FileDetail(
        id=row["id"],
        url=row["url"],
        content_hash=row["content_hash"],
        platform=row["platform"],
        indexed_at=row["indexed_at"],
        tags=row["tags"],
        has_secrets=row["has_secrets"],
        raw_content=row["raw_content"],
        secret_findings=findings,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/dorks
# ---------------------------------------------------------------------------


@app.get("/api/v1/dorks", response_model=list[DorkItem], tags=["discovery"])
def list_dorks(
    type: str = Query(
        "google",
        description="Query set to return: google | s3 | github | gitlab",
    ),
) -> list[DorkItem]:
    """Return the generated search queries / dorks for the requested type."""
    generators: dict[str, object] = {
        "google": GoogleDorkGenerator(),
        "s3": S3DorkGenerator(),
        "github": GitHubQueryGenerator(),
        "gitlab": GitLabQueryGenerator(),
    }
    gen = generators.get(type)
    if gen is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown type '{type}'. Valid values: {list(generators)}",
        )
    queries = gen.all_queries() if hasattr(gen, "all_queries") else gen.all_dorks()
    return [
        DorkItem(
            query=q.query,
            description=q.description,
            tags=q.tags,
            platform=q.platform if hasattr(q, "platform") else (q.tags[0] if q.tags else "general"),
        )
        for q in queries
    ]


# ---------------------------------------------------------------------------
# POST /api/v1/scan  — launch background scan job
# ---------------------------------------------------------------------------


@app.post("/api/v1/scan", response_model=JobStatus, status_code=202, tags=["scan"])
async def start_scan(
    body: ScanRequest,
    background_tasks: BackgroundTasks,
) -> JobStatus:
    """
    Start an asynchronous scan pipeline.

    Pass a list of ``urls`` and/or set ``github_search``/``gitlab_search``
    to discover additional URLs via the respective APIs.
    """
    job_id = str(uuid.uuid4())
    status = JobStatus(job_id=job_id, status="queued")
    _jobs[job_id] = status
    background_tasks.add_task(_run_scan, job_id, body)
    return status


async def _run_scan(job_id: str, body: ScanRequest) -> None:
    """Background coroutine that runs the full extraction / classification pipeline."""
    job = _jobs[job_id]
    job.status = "running"
    try:
        storage = _storage()
        processor = FileProcessor()
        scanner = SecretScanner()

        # Start with provided URLs
        urls: list[str] = list(body.urls)

        async with FileExtractor(github_token=body.github_token) as extractor:
            if body.github_search:
                gh_gen = GitHubQueryGenerator()
                for sq in gh_gen.all_queries():
                    found = await extractor.search_github(sq.query, per_page=10)
                    urls.extend(found)

            if body.gitlab_search:
                gl_gen = GitLabQueryGenerator()
                for sq in gl_gen.all_queries():
                    found = await extractor.search_gitlab(
                        sq.query, per_page=10, gitlab_token=body.gitlab_token
                    )
                    urls.extend(found)

            urls = list(dict.fromkeys(urls))  # deduplicate
            job.total = len(urls)
            extracted = await extractor.fetch_many(urls, concurrency=5)

        saved = 0
        for ef in extracted:
            if not ef.is_valid:
                continue
            processed = processor.process(ef)
            storage.save(processed)
            saved += 1

        job.saved = saved
        job.status = "done"
        job.message = f"Saved {saved}/{len(extracted)} file(s)."
    except Exception as exc:  # noqa: BLE001
        _log.exception("Scan job %s failed", job_id)
        job.status = "error"
        job.error = str(exc)


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id}
# ---------------------------------------------------------------------------


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatus, tags=["scan"])
def get_job(job_id: str) -> JobStatus:
    """Poll the status of a scan or crawl job."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# POST /api/v1/crawl  — launch background crawl job
# ---------------------------------------------------------------------------


@app.post("/api/v1/crawl", response_model=JobStatus, status_code=202, tags=["scan"])
async def start_crawl(
    body: CrawlRequest,
    background_tasks: BackgroundTasks,
) -> JobStatus:
    """
    Start an asynchronous crawl that discovers AI config file URLs via the
    GitHub / GitLab APIs and/or direct path enumeration on a target domain,
    then appends the results to the configured URLs file.
    """
    job_id = str(uuid.uuid4())
    status = JobStatus(job_id=job_id, status="queued")
    _jobs[job_id] = status
    background_tasks.add_task(_run_crawl, job_id, body)
    return status


async def _run_crawl(job_id: str, body: CrawlRequest) -> None:
    """Background coroutine that runs the URL-discovery crawler."""
    job = _jobs[job_id]
    job.status = "running"
    try:
        crawler = Crawler(
            github_token=body.github_token,
            gitlab_token=body.gitlab_token,
        )
        new_urls = await crawler.crawl(
            urls_file=body.urls_file,
            target_url=body.target_url,
            use_github=body.use_github,
            use_gitlab=body.use_gitlab,
            max_queries=body.max_queries,
            check_reachability=True,
        )
        job.saved = len(new_urls)
        job.status = "done"
        job.message = f"Discovered {len(new_urls)} new URL(s) → '{body.urls_file}'."
    except Exception as exc:  # noqa: BLE001
        _log.exception("Crawl job %s failed", job_id)
        job.status = "error"
        job.error = str(exc)


# ---------------------------------------------------------------------------
# GET /api/v1/search  — semantic vector search
# ---------------------------------------------------------------------------


@app.get("/api/v1/search", response_model=list[SearchResult], tags=["discovery"])
def semantic_search(
    q: str = Query(..., description="Natural-language query"),
    n_results: int = Query(10, ge=1, le=50, description="Number of results"),
) -> list[SearchResult]:
    """
    Perform a semantic search against the ChromaDB vector store.

    Requires the vector store to have been populated via a previous scan
    (``VECTOR_DB_PATH`` environment variable must point to the store directory).
    """
    if _VECTOR_DB_PATH is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Vector store is not configured. "
                "Set the VECTOR_DB_PATH environment variable and re-index."
            ),
        )
    vector_store = VectorStore(persist_directory=_VECTOR_DB_PATH)
    hits = vector_store.search(q, n_results=n_results)
    return [
        SearchResult(
            url=h["url"],
            platform=h["platform"],
            tags=h.get("tags", ""),
            distance=h["distance"],
            has_secrets=bool(h.get("has_secrets", False)),
            document_excerpt=h["document"][:300],
        )
        for h in hits
    ]
