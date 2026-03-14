"""
extractor.py — Async HTTP fetching + content extraction module.

Responsibilities:
  - Fetch raw file content from a URL (GitHub raw, direct URLs, …).
  - Extract candidate "System Prompt" blocks using regex / BeautifulSoup.
  - Return a structured ExtractedFile object.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=20)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AI-FINDER/0.1; "
        "+https://github.com/qemm/AI-FINDER)"
    )
}

# Regex patterns to locate system-prompt blocks inside a file
_SYSTEM_PROMPT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:system\s*prompt|system_prompt)\s*[:=]\s*[\"']?(.*?)[\"']?\s*(?:\n|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:##?\s*(?:Instructions?|Rules?|Prompt|System\s*Prompt))\s*\n+(.*?)(?=\n##?|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"<system>(.*?)</system>",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:You are|Act as|Assistant is)\s.{0,400}",
        re.IGNORECASE | re.DOTALL,
    ),
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ExtractedFile:
    """Holds everything extracted from a single URL."""

    url: str
    raw_content: str
    content_hash: str
    system_prompt_blocks: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None

    # Populated by the processor
    platform: str = "unknown"
    tags: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.error is None and bool(self.raw_content)


# ---------------------------------------------------------------------------
# Helpers: convert platform HTML URLs → raw content URLs
# ---------------------------------------------------------------------------


def github_html_to_raw(url: str) -> str:
    """Convert a GitHub HTML blob URL to its raw content equivalent.

    Examples
    --------
    https://github.com/user/repo/blob/main/CLAUDE.md
      → https://raw.githubusercontent.com/user/repo/main/CLAUDE.md
    """
    parsed = urlparse(url)
    if parsed.netloc == "github.com":
        # /user/repo/blob/branch/path  →  remove 'blob' segment
        parts = parsed.path.lstrip("/").split("/")
        if len(parts) >= 4 and parts[2] == "blob":
            raw_path = "/".join(parts[:2] + parts[3:])
            return f"https://raw.githubusercontent.com/{raw_path}"
    return url  # already raw or not a GitHub blob URL


def gitlab_html_to_raw(url: str) -> str:
    """Convert a GitLab HTML blob URL to its raw content equivalent.

    Works for gitlab.com, subdomains of gitlab.com, and self-hosted GitLab
    instances that follow the standard ``/-/blob/`` URL pattern.

    Examples
    --------
    https://gitlab.com/user/repo/-/blob/main/CLAUDE.md
      → https://gitlab.com/user/repo/-/raw/main/CLAUDE.md
    """
    parsed = urlparse(url)
    # The /-/blob/ pattern is unique to GitLab; matching it covers
    # gitlab.com, *.gitlab.com, and any self-hosted instance.
    if "/-/blob/" in parsed.path:
        raw_path = parsed.path.replace("/-/blob/", "/-/raw/", 1)
        return f"{parsed.scheme}://{parsed.netloc}{raw_path}"
    return url


def bitbucket_html_to_raw(url: str) -> str:
    """Convert a Bitbucket HTML src URL to its raw content equivalent.

    Examples
    --------
    https://bitbucket.org/user/repo/src/main/CLAUDE.md
      → https://bitbucket.org/user/repo/raw/main/CLAUDE.md
    """
    parsed = urlparse(url)
    if parsed.netloc == "bitbucket.org":
        parts = parsed.path.lstrip("/").split("/")
        # /user/repo/src/branch/path → /user/repo/raw/branch/path
        if len(parts) >= 4 and parts[2] == "src":
            parts[2] = "raw"
            raw_path = "/".join(parts)
            return f"https://bitbucket.org/{raw_path}"
    return url


def to_raw_url(url: str) -> str:
    """Dispatch to the appropriate platform raw-URL converter.

    Supports GitHub, GitLab and Bitbucket blob/src URLs; returns the
    URL unchanged for any other host or already-raw address.

    GitLab is identified by the ``/-/blob/`` path pattern, which is unique
    to GitLab and works for gitlab.com, subdomains, and self-hosted instances.
    """
    parsed = urlparse(url)
    netloc = parsed.netloc
    if netloc == "github.com":
        return github_html_to_raw(url)
    if "/-/blob/" in parsed.path:
        return gitlab_html_to_raw(url)
    if netloc == "bitbucket.org":
        return bitbucket_html_to_raw(url)
    return url


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class FileExtractor:
    """Async extractor: fetches URLs and parses content."""

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
        headers: dict = DEFAULT_HEADERS,
        github_token: Optional[str] = None,
    ) -> None:
        self._session = session
        self._owns_session = session is None
        self._timeout = timeout
        self._headers = dict(headers)
        if github_token:
            self._headers["Authorization"] = f"token {github_token}"

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "FileExtractor":
        if self._owns_session:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout, headers=self._headers
            )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_session and self._session:
            await self._session.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(self, url: str) -> ExtractedFile:
        """Fetch *url* and return an :class:`ExtractedFile`."""
        raw_url = to_raw_url(url)
        try:
            assert self._session is not None, "Call inside async context manager"
            async with self._session.get(raw_url) as resp:
                resp.raise_for_status()
                text = await resp.text(errors="replace")
        except Exception as exc:  # noqa: BLE001
            return ExtractedFile(
                url=url,
                raw_content="",
                content_hash="",
                error=str(exc),
            )

        content_hash = hashlib.sha256(text.encode()).hexdigest()
        blocks = self._extract_system_prompts(text)

        return ExtractedFile(
            url=url,
            raw_content=text,
            content_hash=content_hash,
            system_prompt_blocks=blocks,
            metadata={"raw_url": raw_url, "length": len(text)},
        )

    async def fetch_many(
        self, urls: list[str], concurrency: int = 10
    ) -> list[ExtractedFile]:
        """Fetch multiple URLs with bounded concurrency."""
        semaphore = asyncio.Semaphore(concurrency)

        async def _fetch_one(url: str) -> ExtractedFile:
            async with semaphore:
                return await self.fetch(url)

        return await asyncio.gather(*(_fetch_one(u) for u in urls))

    # ------------------------------------------------------------------
    # GitHub API helpers
    # ------------------------------------------------------------------

    async def search_github(
        self, query: str, per_page: int = 30, page: int = 1
    ) -> list[str]:
        """Call the GitHub Code Search API and return raw-content URLs.

        Requires a GitHub token in the Authorization header for best results.
        Returns an empty list on error (rate-limit, network, etc.).
        """
        params = {"q": query, "per_page": per_page, "page": page}
        api_url = "https://api.github.com/search/code"
        try:
            assert self._session is not None
            async with self._session.get(
                api_url,
                params=params,
                headers={**self._headers, "Accept": "application/vnd.github+json"},
            ) as resp:
                if resp.status in (403, 422, 503):
                    return []
                resp.raise_for_status()
                data = await resp.json()
        except Exception:  # noqa: BLE001
            return []

        urls: list[str] = []
        for item in data.get("items", []):
            html_url = item.get("html_url", "")
            if html_url:
                urls.append(to_raw_url(html_url))
        return urls

    async def search_gitlab(
        self,
        query: str,
        per_page: int = 20,
        page: int = 1,
        gitlab_token: Optional[str] = None,
    ) -> list[str]:
        """Call the GitLab Code Search API and return raw-content URLs.

        Uses the GitLab Projects search endpoint (blobs scope).
        Requires a GitLab personal access token for best results.
        Returns an empty list on error.

        Reference: https://docs.gitlab.com/ee/api/search.html
        """
        params = {
            "scope": "blobs",
            "search": query,
            "per_page": per_page,
            "page": page,
        }
        api_url = "https://gitlab.com/api/v4/search"
        extra_headers: dict[str, str] = {}
        if gitlab_token:
            extra_headers["PRIVATE-TOKEN"] = gitlab_token
        try:
            assert self._session is not None
            async with self._session.get(
                api_url,
                params=params,
                headers={**self._headers, **extra_headers},
            ) as resp:
                if resp.status in (401, 403, 422, 503):
                    return []
                resp.raise_for_status()
                items = await resp.json()
        except Exception:  # noqa: BLE001
            return []

        urls: list[str] = []
        for item in items if isinstance(items, list) else []:
            project_id = item.get("project_id")
            path = item.get("path", "")
            ref = item.get("ref", "HEAD")
            if project_id and path:
                raw = (
                    f"https://gitlab.com/api/v4/projects/{project_id}"
                    f"/repository/files/{path.replace('/', '%2F')}/raw"
                    f"?ref={ref}"
                )
                urls.append(raw)
        return urls

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_system_prompts(text: str) -> list[str]:
        """Return a deduplicated list of candidate system-prompt blocks."""
        blocks: list[str] = []
        seen: set[str] = set()

        # Try each regex pattern
        for pattern in _SYSTEM_PROMPT_PATTERNS:
            for match in pattern.finditer(text):
                block = match.group(0).strip()
                if block and block not in seen:
                    seen.add(block)
                    blocks.append(block)

        # Also try BeautifulSoup for HTML-wrapped content
        if "<" in text:
            try:
                soup = BeautifulSoup(text, "lxml")
                for tag in soup.find_all(["system", "prompt", "instructions"]):
                    block = tag.get_text(strip=True)
                    if block and block not in seen:
                        seen.add(block)
                        blocks.append(block)
            except Exception:  # noqa: BLE001
                pass

        return blocks
