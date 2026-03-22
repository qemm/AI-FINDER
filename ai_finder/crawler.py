"""
crawler.py — URL discovery and crawling module.

Searches GitHub and GitLab Code Search APIs using the query strings generated
by :mod:`ai_finder.discovery` to find AI agent configuration file URLs.
Also supports path enumeration against a target domain URL — similar to tools
like gobuster or wfuzz — by probing well-known AI config file paths directly.
Each candidate URL is checked for HTTP reachability; confirmed URLs are
merged into a ``urls.txt`` file (one URL per line) so the rest of the
pipeline can consume them.

Typical usage
-------------
    import asyncio
    from ai_finder.crawler import Crawler

    # API-based discovery (GitHub / GitLab search)
    crawler = Crawler(github_token="ghp_…")
    new_urls = asyncio.run(crawler.crawl(urls_file="urls.txt"))
    print(f"Found {len(new_urls)} new URL(s).")

    # Path-enumeration mode (gobuster / wfuzz style)
    new_urls = asyncio.run(
        crawler.crawl(urls_file="urls.txt", target_url="https://example.com")
    )
    print(f"Found {len(new_urls)} new URL(s).")
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp

from ai_finder.discovery import (
    GitHubQueryGenerator,
    GitLabQueryGenerator,
    TARGET_FILENAMES,
    COMMON_DIRECTORIES,
)
from ai_finder.extractor import DEFAULT_HEADERS, DEFAULT_TIMEOUT, FileExtractor
from ai_finder.logger import get_logger, build_trace_config

log = get_logger(__name__)

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
        request_delay: float = 1.0,
    ) -> None:
        self._github_token = github_token
        self._gitlab_token = gitlab_token
        self._concurrency = concurrency
        self._timeout = timeout
        self._request_delay = request_delay

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
        """Return ``True`` if *url* responds with HTTP status 200.

        Only HTTP 200 is accepted; 401, 403, and other non-200 responses are
        treated as unreachable.  Falls back to a GET request if HEAD is not
        allowed (405).
        """
        log.debug("check_url  url=%s", url)
        try:
            async with session.head(
                url, allow_redirects=True, raise_for_status=False
            ) as resp:
                if resp.status == 405:
                    # Server does not allow HEAD — try GET
                    async with session.get(
                        url, allow_redirects=True, raise_for_status=False
                    ) as gresp:
                        reachable = gresp.status == 200
                        log.debug(
                            "check_url  GET fallback  status=%d  reachable=%s  url=%s",
                            gresp.status,
                            reachable,
                            url,
                        )
                        return reachable
                reachable = resp.status == 200
                log.debug(
                    "check_url  HEAD  status=%d  reachable=%s  url=%s",
                    resp.status,
                    reachable,
                    url,
                )
                return reachable
        except Exception as exc:  # noqa: BLE001
            log.debug("check_url  error  url=%s  error=%s", url, exc)
            return False

    async def filter_reachable(self, urls: list[str]) -> list[str]:
        """Return the subset of *urls* that are HTTP-reachable.

        Requests are made concurrently, bounded by *concurrency*.
        """
        log.info("filter_reachable  checking %d URL(s)", len(urls))
        semaphore = asyncio.Semaphore(self._concurrency)

        async def _check(
            session: aiohttp.ClientSession, url: str
        ) -> tuple[str, bool]:
            async with semaphore:
                ok = await self.check_url(session, url)
                return url, ok

        async with aiohttp.ClientSession(
            timeout=self._timeout,
            headers=DEFAULT_HEADERS,
            trace_configs=[build_trace_config()],
        ) as session:
            results = await asyncio.gather(
                *(_check(session, u) for u in urls)
            )

        reachable = [url for url, ok in results if ok]
        log.info(
            "filter_reachable  done  reachable=%d  total=%d",
            len(reachable),
            len(urls),
        )
        return reachable

    async def enumerate_paths(
        self,
        target_url: str,
        *,
        paths: Optional[list[str]] = None,
        depth: int = 4,
        check_reachability: bool = True,
    ) -> list[str]:
        """Enumerate AI config file paths from *target_url* (gobuster / wfuzz style).

        Constructs candidate URLs by joining *target_url* with each path in
        *paths*.  When *paths* is ``None`` (the default), the method generates
        paths at every directory depth from 0 (root) to *depth* using
        :data:`ai_finder.discovery.COMMON_DIRECTORIES` and
        :data:`ai_finder.discovery.TARGET_FILENAMES`, producing URLs such as::

            https://example.com/CLAUDE.md                  # depth 0
            https://example.com/agents/CLAUDE.md           # depth 1
            https://example.com/agents/config/CLAUDE.md    # depth 2

        When *check_reachability* is ``True`` the candidate list is further
        filtered to URLs that return HTTP 200.

        Parameters
        ----------
        target_url:
            The base URL to start from (e.g. ``https://example.com``).
        paths:
            Explicit list of paths to probe.  When ``None`` (default),
            paths are generated automatically up to *depth* directory levels.
        depth:
            Maximum number of directory components to prepend to each
            filename.  Ignored when *paths* is supplied explicitly.
        check_reachability:
            When ``True`` (the default) each candidate URL is verified via
            an HTTP request before being returned.

        Returns
        -------
        list[str]
            Candidate (and optionally verified reachable) URLs found under
            *target_url*.
        """
        if paths is None:
            paths = build_directory_paths(depth)

        base = target_url.rstrip("/") + "/"
        candidates = [urljoin(base, p.lstrip("/")) for p in paths]

        if check_reachability:
            return await self.filter_reachable(candidates)
        return candidates

    async def crawl(
        self,
        urls_file: str = "urls.txt",
        *,
        target_url: Optional[str] = None,
        use_github: bool = True,
        use_gitlab: bool = True,
        use_web_search: bool = True,
        web_search_engines: tuple[str, ...] = (
            "duckduckgo", "google", "bing", "yandex"
        ),
        web_dork_sources: str = "all",
        max_web_dorks: Optional[int] = None,
        max_queries: Optional[int] = None,
        per_page: int = 30,
        depth: int = 4,
        check_reachability: bool = True,
    ) -> list[str]:
        """Run the full crawl pipeline and update *urls_file*.

        Steps
        -----
        1. Load any URLs already present in *urls_file*.
        2. Discover new candidate URLs via the GitHub / GitLab search APIs.
        3. If *target_url* is provided, enumerate known AI config file paths
           directly against that domain (gobuster / wfuzz style) at up to
           *depth* directory levels deep.
        4. If *use_web_search* is ``True``, submit dork queries to the search
           engines listed in *web_search_engines* and collect result URLs.
           Dork generation is controlled by *web_dork_sources*.
        5. Exclude candidates that already appear in *urls_file*.
        6. Optionally filter candidates to HTTP-200 URLs only.
        7. Merge verified URLs with the existing set and rewrite *urls_file*.

        Parameters
        ----------
        urls_file:
            Path to the text file that holds discovered URLs (one per line).
            The file is created if it does not yet exist.
        target_url:
            Optional base URL of a domain to enumerate AI config file paths
            against (e.g. ``https://example.com``).  When provided, the
            crawler probes paths up to *depth* directory levels deep.
        use_github:
            Enable GitHub Code Search.
        use_gitlab:
            Enable GitLab blob search.
        use_web_search:
            When ``True``, submit dork queries to *web_search_engines* and
            collect URLs from the search result pages.
        web_search_engines:
            Tuple of engine names to use when *use_web_search* is ``True``.
            Valid values: ``"duckduckgo"``, ``"google"``, ``"bing"``,
            ``"yandex"``.
        web_dork_sources:
            Which dork generator(s) to use for web search.  Valid values:

            * ``"github"`` — dorks restricted to ``site:github.com``.
            * ``"web"`` — generic open-web dorks (no host restriction),
              finding AI config files on *any* publicly indexed site.
            * ``"all"`` *(default)* — both sets combined.
        max_web_dorks:
            Cap the number of dork queries sent to each search engine.
            ``None`` means no cap.
        max_queries:
            Cap the number of queries sent per API platform.
        per_page:
            Results per API page call.
        depth:
            Maximum directory depth for target-URL path enumeration.
        check_reachability:
            When ``True`` (the default) each new URL is verified via an HTTP
            request (HTTP 200 only) before being written to *urls_file*.

        Returns
        -------
        list[str]
            The newly discovered URLs that were appended to *urls_file*.
        """
        log.info(
            "crawl  start  urls_file=%s  target_url=%s  github=%s  gitlab=%s"
            "  web_search=%s  dork_sources=%s  max_queries=%s"
            "  depth=%d  check_reachability=%s",
            urls_file,
            target_url,
            use_github,
            use_gitlab,
            use_web_search,
            web_dork_sources,
            max_queries,
            depth,
            check_reachability,
        )
        existing = load_urls(urls_file)
        log.info("crawl  existing_urls=%d  file=%s", len(existing), urls_file)

        candidates = await self.discover_urls(
            use_github=use_github,
            use_gitlab=use_gitlab,
            max_queries=max_queries,
            per_page=per_page,
        )
        log.info("crawl  api_candidates=%d", len(candidates))

        # Path enumeration against the target domain (gobuster / wfuzz style)
        if target_url:
            log.info("crawl  enumerate_paths  target=%s  depth=%d", target_url, depth)
            path_candidates = await self.enumerate_paths(
                target_url, check_reachability=False, depth=depth
            )
            log.info("crawl  path_candidates=%d", len(path_candidates))
            candidates.extend(path_candidates)

        # Web search dorking across multiple search engines
        if use_web_search:
            log.info(
                "crawl  web_search  engines=%s  dork_sources=%s",
                web_search_engines,
                web_dork_sources,
            )
            # Deferred import avoids a hard dependency on web_search for users
            # who never enable this feature, and prevents any circular-import risk.
            from ai_finder.web_search import WebSearcher  # noqa: PLC0415

            async with WebSearcher(
                timeout=self._timeout, request_delay=self._request_delay
            ) as searcher:
                web_urls = await searcher.search_with_dorks(
                    engines=web_search_engines,
                    max_dorks=max_web_dorks,
                    dork_sources=web_dork_sources,
                )
            log.info("crawl  web_search_candidates=%d", len(web_urls))
            candidates.extend(web_urls)

        # Deduplicate candidates while preserving order
        candidates = list(dict.fromkeys(candidates))

        # Only process URLs that are not already recorded
        new_candidates = [u for u in candidates if u not in existing]
        log.info(
            "crawl  new_candidates=%d  (total_candidates=%d)",
            len(new_candidates),
            len(candidates),
        )

        if check_reachability and new_candidates:
            new_urls = await self.filter_reachable(new_candidates)
        else:
            new_urls = new_candidates

        if new_urls:
            update_urls_file(urls_file, existing, new_urls)
            log.info("crawl  saved=%d  file=%s", len(new_urls), urls_file)
        else:
            log.info("crawl  no new URLs found")

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
        log.info("_search_github  queries=%d  per_page=%d", len(queries), per_page)
        urls: list[str] = []
        for i, sq in enumerate(queries):
            if i > 0 and self._request_delay > 0:
                await asyncio.sleep(self._request_delay)
            log.debug("_search_github  query=%r", sq.query)
            found = await extractor.search_github(sq.query, per_page=per_page)
            log.debug("_search_github  found=%d  query=%r", len(found), sq.query)
            urls.extend(found)
            # Expand discovered repos into brute-force candidates so that
            # every config filename is tried against each unique repository.
            urls.extend(_brute_force_from_github_urls(found))
        log.info("_search_github  total_urls=%d", len(urls))
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
        log.info("_search_gitlab  queries=%d  per_page=%d", len(queries), per_page)
        urls: list[str] = []
        for i, sq in enumerate(queries):
            if i > 0 and self._request_delay > 0:
                await asyncio.sleep(self._request_delay)
            log.debug("_search_gitlab  query=%r", sq.query)
            found = await extractor.search_gitlab(
                sq.query,
                per_page=per_page,
                gitlab_token=self._gitlab_token,
            )
            log.debug("_search_gitlab  found=%d  query=%r", len(found), sq.query)
            urls.extend(found)
            # Expand discovered repos into brute-force candidates.
            urls.extend(_brute_force_from_gitlab_urls(found))
        log.info("_search_gitlab  total_urls=%d", len(urls))
        return urls


# ---------------------------------------------------------------------------
# Path-generation helpers (module-level for easy unit-testing)
# ---------------------------------------------------------------------------


def build_directory_paths(max_depth: int = 4) -> list[str]:
    """Generate candidate relative file paths at directory depths 0 to *max_depth*.

    At depth 0 the raw :data:`~ai_finder.discovery.TARGET_FILENAMES` are
    returned (files probed directly at the site root).  At each subsequent
    depth level, every unique *permutation* of
    :data:`~ai_finder.discovery.COMMON_DIRECTORIES` of that length is
    prepended to each filename, producing paths such as::

        CLAUDE.md                        # depth 0
        agents/CLAUDE.md                 # depth 1
        agents/config/CLAUDE.md          # depth 2
        agents/config/prompts/CLAUDE.md  # depth 3

    Using permutations (rather than the full Cartesian product) prevents
    semantically odd paths such as ``agents/agents/CLAUDE.md``.

    Parameters
    ----------
    max_depth:
        Maximum number of directory components to prepend (1-based).
        Depth 0 (root-level filenames) is always included.

    Returns
    -------
    list[str]
        Deduplicated, insertion-ordered list of relative path strings.
    """
    from itertools import permutations as _permutations  # local import is fine

    paths: list[str] = list(TARGET_FILENAMES)  # depth 0

    for depth in range(1, max_depth + 1):
        for dir_combo in _permutations(COMMON_DIRECTORIES, depth):
            prefix = "/".join(dir_combo)
            for fname in TARGET_FILENAMES:
                paths.append(f"{prefix}/{fname}")

    return list(dict.fromkeys(paths))  # deduplicate while preserving order


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


# ---------------------------------------------------------------------------
# Brute-force URL expansion helpers (module-level for easy unit-testing)
# ---------------------------------------------------------------------------


def _github_repo_base_from_url(url: str) -> Optional[str]:
    """Extract the repository base URL from a ``raw.githubusercontent.com`` URL.

    Returns ``None`` when *url* does not match the expected pattern.

    Example
    -------
    ``https://raw.githubusercontent.com/owner/repo/main/CLAUDE.md``
    → ``"https://raw.githubusercontent.com/owner/repo/main"``
    """
    parsed = urlparse(url)
    if parsed.netloc != "raw.githubusercontent.com":
        return None
    parts = parsed.path.lstrip("/").split("/")
    # Minimum: owner / repo / branch / filename
    if len(parts) < 4:
        return None
    owner, repo, branch = parts[0], parts[1], parts[2]
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"


def _gitlab_repo_base_from_url(url: str) -> Optional[str]:
    """Extract the repository base URL from a GitLab raw-content URL.

    Returns ``None`` when *url* does not match the ``/-/raw/`` pattern.

    Example
    -------
    ``https://gitlab.com/group/project/-/raw/main/CLAUDE.md``
    → ``"https://gitlab.com/group/project/-/raw/main"``
    """
    parsed = urlparse(url)
    if "/-/raw/" not in parsed.path:
        return None
    before, after = parsed.path.split("/-/raw/", 1)
    branch = after.split("/")[0]
    if not branch:
        return None
    return f"{parsed.scheme}://{parsed.netloc}{before}/-/raw/{branch}"


def _brute_force_from_github_urls(urls: list[str]) -> list[str]:
    """Expand a list of GitHub file URLs into brute-force candidate URLs.

    For each unique repository base discovered in *urls*, all
    :data:`~ai_finder.discovery.TARGET_FILENAMES` are appended to that base
    so that the config file name is always the last URL component.

    Parameters
    ----------
    urls:
        Raw ``raw.githubusercontent.com`` URLs already discovered via the
        GitHub Code Search API.

    Returns
    -------
    list[str]
        Deduplicated list of additional candidate raw-content URLs.
    """
    bases: set[str] = set()
    for url in urls:
        base = _github_repo_base_from_url(url)
        if base:
            bases.add(base)

    result: list[str] = []
    seen: set[str] = set(urls)
    for base in sorted(bases):
        for fname in TARGET_FILENAMES:
            candidate = f"{base}/{fname}"
            if candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
    return result


def _brute_force_from_gitlab_urls(urls: list[str]) -> list[str]:
    """Expand a list of GitLab file URLs into brute-force candidate URLs.

    For each unique repository base discovered in *urls*, all
    :data:`~ai_finder.discovery.TARGET_FILENAMES` are appended to that base
    so that the config file name is always the last URL component.

    Parameters
    ----------
    urls:
        GitLab raw-content URLs already discovered via the GitLab Search API.

    Returns
    -------
    list[str]
        Deduplicated list of additional candidate raw-content URLs.
    """
    bases: set[str] = set()
    for url in urls:
        base = _gitlab_repo_base_from_url(url)
        if base:
            bases.add(base)

    result: list[str] = []
    seen: set[str] = set(urls)
    for base in sorted(bases):
        for fname in TARGET_FILENAMES:
            candidate = f"{base}/{fname}"
            if candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
    return result
