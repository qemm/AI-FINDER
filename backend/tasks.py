from __future__ import annotations

import asyncio
import sys
import os

# Ensure ai_finder is importable when running inside the container
sys.path.insert(0, "/app")

from ai_finder.crawler import Crawler
from ai_finder.extractor import FileExtractor
from ai_finder.processor import FileProcessor
from ai_finder.scanner import SecretScanner
from ai_finder.storage import Storage
from ai_finder.vector_store import VectorStore

from backend.config import Settings
from backend.job_store import store
from backend.schemas import CrawlJobRequest, ScanJobRequest


async def run_crawl_job(job_id: str, request: CrawlJobRequest, settings: Settings) -> None:
    """Full crawl pipeline: discover URLs → fetch → process → store → index."""
    store.set_running(job_id)
    stats: dict = {"urls_found": 0, "files_stored": 0, "secrets_found": 0, "errors": 0}

    try:
        github_token = request.github_token or settings.github_token
        gitlab_token = request.gitlab_token or settings.gitlab_token

        crawler = Crawler(
            github_token=github_token,
            gitlab_token=gitlab_token,
            captcha_pause=False,
        )

        await store.emit(job_id, "status", {"phase": "crawling"})

        new_urls = await crawler.crawl(
            urls_file=settings.urls_file,
            target_url=request.target_url,
            use_github=request.use_github,
            use_gitlab=request.use_gitlab,
            use_web_search=request.use_web_search,
            web_search_engines=tuple(request.engines),
            web_dork_sources=request.web_dork_sources,
            max_web_dorks=request.max_web_dorks,
            max_queries=request.max_queries,
            depth=request.depth,
            check_reachability=request.check_reachability,
        )

        stats["urls_found"] = len(new_urls)
        for url in new_urls:
            await store.emit(job_id, "new_url", {"url": url})

        await _process_urls(job_id, new_urls, settings, stats)

    except Exception as exc:  # noqa: BLE001
        store.set_error(job_id, str(exc))
        return

    store.set_done(job_id, stats)


async def run_scan_job(job_id: str, request: ScanJobRequest, settings: Settings) -> None:
    """Scan a caller-supplied list of URLs without crawling."""
    store.set_running(job_id)
    stats: dict = {"urls_found": len(request.urls), "files_stored": 0, "secrets_found": 0, "errors": 0}

    try:
        await _process_urls(job_id, request.urls, settings, stats)
    except Exception as exc:  # noqa: BLE001
        store.set_error(job_id, str(exc))
        return

    store.set_done(job_id, stats)


async def _process_urls(
    job_id: str,
    urls: list[str],
    settings: Settings,
    stats: dict,
) -> None:
    """Fetch, classify, scan for secrets, store, and index a list of URLs."""
    if not urls:
        return

    await store.emit(job_id, "status", {"phase": "fetching"})

    storage = Storage(db_path=settings.db_path)
    vector_store = VectorStore(persist_directory=settings.vector_db_path)
    processor = FileProcessor()
    scanner = SecretScanner()

    async with FileExtractor() as extractor:
        extracted_files = await extractor.fetch_many(urls, concurrency=10)

    await store.emit(job_id, "status", {"phase": "processing"})

    for ef in extracted_files:
        if not ef.is_valid:
            stats["errors"] += 1
            await store.emit(job_id, "error", {"url": ef.url, "error": ef.error})
            continue

        processed = processor.process(ef)
        file_id = storage.save(processed)

        if file_id is None:
            stats["errors"] += 1
            continue

        stats["files_stored"] += 1

        # Secret detection result for the event
        secret_report = scanner.report(ef.raw_content, ef.url)
        secret_count = secret_report["secret_count"]
        if secret_count:
            stats["secrets_found"] += secret_count
            for finding in secret_report["findings"]:
                await store.emit(job_id, "secret", {
                    "url": ef.url,
                    "rule": finding["rule"],
                    "line": finding["line"],
                    "redacted": finding["redacted"],
                })

        await store.emit(job_id, "new_file", {
            "file_id": file_id,
            "url": ef.url,
            "platform": processed.platform,
            "has_secrets": bool(secret_count),
            "secret_count": secret_count,
            "tags": processed.tags,
        })

        # Index in vector store (best-effort)
        try:
            vector_store.add(processed)
        except Exception:  # noqa: BLE001
            pass
