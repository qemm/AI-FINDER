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
# Helper: convert GitHub HTML URL → raw content URL
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
        raw_url = github_html_to_raw(url)
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
                urls.append(github_html_to_raw(html_url))
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
