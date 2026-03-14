"""
crawler.py — URL discovery and crawling module.

Searches GitHub and GitLab Code Search APIs using the query strings generated
by :mod:`ai_finder.discovery` to find AI agent configuration file URLs.
Each candidate URL is checked for HTTP reachability; confirmed URLs are
merged into a ``urls.txt`` file (one URL per line) so the rest of the
pipeline can consume them.

Typical usage
-------------
    import asyncio
    from ai_finder.crawler import Crawler

    crawler = Crawler(github_token="ghp_…")
    new_urls = asyncio.run(crawler.crawl(urls_file="urls.txt"))
    print(f"Found {len(new_urls)} new URL(s).")
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import aiohttp

from ai_finder.discovery import GitHubQueryGenerator, GitLabQueryGenerator
from ai_finder.extractor import DEFAULT_HEADERS, DEFAULT_TIMEOUT, FileExtractor

# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------


class Crawler:
    """Discover AI agent config-file URLs via API search and reachability checks.

    Parameters
    ----------
    github_token:
        Optional GitHub personal access token.  Raises the GitHub Code Search
        API rate limit from 10 req/min (unauthenticated) to 30 req/min.
    gitlab_token:
        Optional GitLab personal access token.  Required for private projects;
        increases rate limits for public searches.
    concurrency:
        Maximum number of simultaneous HTTP connections used during the
        reachability check phase.
    timeout:
        ``aiohttp.ClientTimeout`` applied to every HTTP request.
    """

    def __init__(
        self,
        github_token: Optional[str] = None,
        gitlab_token: Optional[str] = None,
        concurrency: int = 10,
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._github_token = github_token
        self._gitlab_token = gitlab_token
        self._concurrency = concurrency
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def discover_urls(
        self,
        *,
        use_github: bool = True,
        use_gitlab: bool = True,
        max_queries: Optional[int] = None,
        per_page: int = 30,
    ) -> list[str]:
        """Search GitHub / GitLab APIs and return deduplicated candidate URLs.

        Parameters
        ----------
        use_github:
            Enable GitHub Code Search.
        use_gitlab:
            Enable GitLab blob search.
        max_queries:
            Cap the number of search queries sent to each platform.  ``None``
            means no limit (all generated queries are used).
        per_page:
            Results requested per API page call.

        Returns
        -------
        list[str]
            Deduplicated list of raw-content URLs discovered across all
            enabled platforms.
        """
        found: list[str] = []

        async with FileExtractor(
            github_token=self._github_token,
            timeout=self._timeout,
        ) as extractor:
            if use_github:
                found.extend(
                    await self._search_github(extractor, max_queries, per_page)
                )
            if use_gitlab:
                found.extend(
                    await self._search_gitlab(extractor, max_queries, per_page)
                )

        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for url in found:
            if url not in seen:
                seen.add(url)
                deduped.append(url)
        return deduped

    async def check_url(self, session: aiohttp.ClientSession, url: str) -> bool:
        """Return ``True`` if *url* responds with an HTTP status < 400.

        Falls back to a GET request if HEAD is not allowed (405).
        """
        try:
            async with session.head(
                url, allow_redirects=True, raise_for_status=False
            ) as resp:
                if resp.status == 405:
                    # Server does not allow HEAD — try GET
                    async with session.get(
                        url, allow_redirects=True, raise_for_status=False
                    ) as gresp:
                        return gresp.status < 400
                return resp.status < 400
        except Exception:  # noqa: BLE001
            return False

    async def filter_reachable(self, urls: list[str]) -> list[str]:
        """Return the subset of *urls* that are HTTP-reachable.

        Requests are made concurrently, bounded by *concurrency*.
        """
        semaphore = asyncio.Semaphore(self._concurrency)

        async def _check(
            session: aiohttp.ClientSession, url: str
        ) -> tuple[str, bool]:
            async with semaphore:
                ok = await self.check_url(session, url)
                return url, ok

        async with aiohttp.ClientSession(
            timeout=self._timeout, headers=DEFAULT_HEADERS
        ) as session:
            results = await asyncio.gather(
                *(_check(session, u) for u in urls)
            )

        return [url for url, ok in results if ok]

    async def crawl(
        self,
        urls_file: str = "urls.txt",
        *,
        use_github: bool = True,
        use_gitlab: bool = True,
        max_queries: Optional[int] = None,
        per_page: int = 30,
        check_reachability: bool = True,
    ) -> list[str]:
        """Run the full crawl pipeline and update *urls_file*.

        Steps
        -----
        1. Load any URLs already present in *urls_file*.
        2. Discover new candidate URLs via the GitHub / GitLab search APIs.
        3. Exclude candidates that already appear in *urls_file*.
        4. Optionally filter candidates to reachable URLs only.
        5. Merge verified URLs with the existing set and rewrite *urls_file*.

        Parameters
        ----------
        urls_file:
            Path to the text file that holds discovered URLs (one per line).
            The file is created if it does not yet exist.
        use_github:
            Enable GitHub Code Search.
        use_gitlab:
            Enable GitLab blob search.
        max_queries:
            Cap the number of queries sent per platform.
        per_page:
            Results per API page call.
        check_reachability:
            When ``True`` (the default) each new URL is verified via an HTTP
            HEAD request before being written to *urls_file*.

        Returns
        -------
        list[str]
            The newly discovered URLs that were appended to *urls_file*.
        """
        existing = load_urls(urls_file)
        candidates = await self.discover_urls(
            use_github=use_github,
            use_gitlab=use_gitlab,
            max_queries=max_queries,
            per_page=per_page,
        )

        # Only process URLs that are not already recorded
        new_candidates = [u for u in candidates if u not in existing]

        if check_reachability and new_candidates:
            new_urls = await self.filter_reachable(new_candidates)
        else:
            new_urls = new_candidates

        if new_urls:
            update_urls_file(urls_file, existing, new_urls)

        return new_urls

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _search_github(
        self,
        extractor: FileExtractor,
        max_queries: Optional[int],
        per_page: int,
    ) -> list[str]:
        gen = GitHubQueryGenerator()
        queries = gen.all_queries()
        if max_queries is not None:
            queries = queries[:max_queries]
        urls: list[str] = []
        for sq in queries:
            found = await extractor.search_github(sq.query, per_page=per_page)
            urls.extend(found)
        return urls

    async def _search_gitlab(
        self,
        extractor: FileExtractor,
        max_queries: Optional[int],
        per_page: int,
    ) -> list[str]:
        gen = GitLabQueryGenerator()
        queries = gen.all_queries()
        if max_queries is not None:
            queries = queries[:max_queries]
        urls: list[str] = []
        for sq in queries:
            found = await extractor.search_gitlab(
                sq.query,
                per_page=per_page,
                gitlab_token=self._gitlab_token,
            )
            urls.extend(found)
        return urls


# ---------------------------------------------------------------------------
# File helpers (module-level for easy unit-testing)
# ---------------------------------------------------------------------------


def load_urls(path: str) -> set[str]:
    """Load URLs from *path* (one per line).

    Lines that are blank or start with ``#`` are ignored.
    Returns an empty set if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        return set()
    return {
        line.strip()
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def update_urls_file(path: str, existing: set[str], new_urls: list[str]) -> None:
    """Merge *new_urls* into the URL file at *path*.

    The resulting file contains the union of *existing* and *new_urls*,
    sorted alphabetically, one URL per line.
    """
    all_urls = sorted(existing | set(new_urls))
    Path(path).write_text("\n".join(all_urls) + "\n", encoding="utf-8")
