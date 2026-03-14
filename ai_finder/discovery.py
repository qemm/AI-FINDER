"""
discovery.py — Search-query / dork generation module.

Produces:
  - Google dork strings targeting AI agent config files.
  - GitHub Code Search API query strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


# ---------------------------------------------------------------------------
# File-pattern catalogue
# ---------------------------------------------------------------------------

#: Well-known AI agent / assistant configuration file names.
TARGET_FILENAMES: list[str] = [
    "CLAUDE.md",
    "AGENTS.md",
    ".cursorrules",
    "CURSOR.md",
    ".clinerules",
    "COPILOT.md",
    ".github/copilot-instructions.md",
    "system_prompt.md",
    "system_prompt.txt",
    "langchain_config.py",
    "langchain_config.yaml",
    "langchain_config.json",
    "crewai_config.yaml",
    "crewai_config.json",
    ".env.agents",
    "agent_config.json",
    "agent_config.yaml",
    "openai_config.json",
]

#: Unique text fragments that reliably appear inside these files.
CONTENT_SIGNATURES: list[str] = [
    "Assistant is a large language model trained by Anthropic",
    "You are an expert developer",
    "Rules for the agent",
    "You are a helpful assistant",
    "You are Claude",
    "Act as an AI assistant",
    "SYSTEM PROMPT",
    "System prompt:",
    "## Instructions",
    "## Rules",
    "langchain",
    "crewai",
    "openai.api_key",
    "anthropic_api_key",
]

#: Path prefixes worth targeting.
TARGET_PATHS: list[str] = [
    ".github/",
    ".cursor/",
    "prompts/",
    "agents/",
    "config/",
    "src/agents/",
    "docs/",
]


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class SearchQuery:
    """A single, platform-specific search query."""

    platform: str  # "google" | "github"
    query: str
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.query


# ---------------------------------------------------------------------------
# Google Dork generator
# ---------------------------------------------------------------------------


class GoogleDorkGenerator:
    """Generates Google dork strings for AI agent config files."""

    # Dork operator templates
    _FILENAME_TMPL = 'intitle:"{fname}" site:github.com'
    _CONTENT_TMPL = '"{signature}" (filetype:md OR filetype:txt OR filetype:yaml OR filetype:json) site:github.com'
    _PATH_TMPL = 'inurl:"{path}" site:github.com (filetype:md OR filetype:txt)'
    _COMBINED_TMPL = 'intitle:"{fname}" "{signature}" site:github.com'

    def filename_dorks(self) -> Iterator[SearchQuery]:
        """One dork per target filename."""
        for fname in TARGET_FILENAMES:
            yield SearchQuery(
                platform="google",
                query=self._FILENAME_TMPL.format(fname=fname),
                description=f"Google dork for filename: {fname}",
                tags=["filename", fname],
            )

    def content_dorks(self) -> Iterator[SearchQuery]:
        """One dork per content signature."""
        for sig in CONTENT_SIGNATURES:
            yield SearchQuery(
                platform="google",
                query=self._CONTENT_TMPL.format(signature=sig),
                description=f"Google dork for content signature: {sig!r}",
                tags=["content-signature"],
            )

    def path_dorks(self) -> Iterator[SearchQuery]:
        """One dork per target path prefix."""
        for path in TARGET_PATHS:
            yield SearchQuery(
                platform="google",
                query=self._PATH_TMPL.format(path=path),
                description=f"Google dork for path prefix: {path}",
                tags=["path"],
            )

    def combined_dorks(self) -> Iterator[SearchQuery]:
        """Cross-product of key filenames × key signatures."""
        priority_files = ["CLAUDE.md", "AGENTS.md", ".cursorrules"]
        priority_sigs = [
            "You are an expert developer",
            "Rules for the agent",
            "Assistant is a large language model trained by Anthropic",
        ]
        for fname in priority_files:
            for sig in priority_sigs:
                yield SearchQuery(
                    platform="google",
                    query=self._COMBINED_TMPL.format(fname=fname, signature=sig),
                    description=f"Combined dork: {fname} + signature",
                    tags=["combined", fname],
                )

    def all_dorks(self) -> list[SearchQuery]:
        """Return the full dork list, deduplicated."""
        seen: set[str] = set()
        result: list[SearchQuery] = []
        for gen in (
            self.filename_dorks,
            self.content_dorks,
            self.path_dorks,
            self.combined_dorks,
        ):
            for dork in gen():
                if dork.query not in seen:
                    seen.add(dork.query)
                    result.append(dork)
        return result


# ---------------------------------------------------------------------------
# GitHub Code Search query generator
# ---------------------------------------------------------------------------


class GitHubQueryGenerator:
    """Generates GitHub Code Search API query strings.

    Reference: https://docs.github.com/en/search-github/github-code-search/understanding-github-code-search-syntax
    """

    def filename_queries(self) -> Iterator[SearchQuery]:
        for fname in TARGET_FILENAMES:
            # Strip path component — GitHub `filename:` matches the basename
            basename = fname.split("/")[-1]
            yield SearchQuery(
                platform="github",
                query=f"filename:{basename}",
                description=f"GitHub search for filename: {basename}",
                tags=["filename", basename],
            )

    def content_queries(self) -> Iterator[SearchQuery]:
        for sig in CONTENT_SIGNATURES:
            yield SearchQuery(
                platform="github",
                query=f'"{sig}"',
                description=f"GitHub content search for: {sig!r}",
                tags=["content-signature"],
            )

    def path_queries(self) -> Iterator[SearchQuery]:
        for path in TARGET_PATHS:
            yield SearchQuery(
                platform="github",
                query=f"path:{path}",
                description=f"GitHub path search: {path}",
                tags=["path"],
            )

    def combined_queries(self) -> Iterator[SearchQuery]:
        """Filename + content combined queries (most precise)."""
        combos = [
            ("CLAUDE.md", "You are"),
            ("AGENTS.md", "Rules for the agent"),
            (".cursorrules", "You are an expert"),
            ("langchain_config.yaml", "langchain"),
            ("crewai_config.yaml", "crewai"),
        ]
        for fname, sig in combos:
            basename = fname.split("/")[-1]
            yield SearchQuery(
                platform="github",
                query=f'filename:{basename} "{sig}"',
                description=f"GitHub combined: {basename} + {sig!r}",
                tags=["combined", basename],
            )

    def extension_queries(self) -> Iterator[SearchQuery]:
        """Search by file extension + content keywords."""
        ext_sigs = [
            ("md", "system prompt"),
            ("md", "CLAUDE"),
            ("cursorrules", "rules"),
            ("yaml", "langchain"),
            ("yaml", "crewai"),
            ("json", "openai"),
        ]
        for ext, kw in ext_sigs:
            yield SearchQuery(
                platform="github",
                query=f'extension:{ext} "{kw}"',
                description=f"GitHub extension search: .{ext} + {kw!r}",
                tags=["extension", ext],
            )

    def all_queries(self) -> list[SearchQuery]:
        """Return full GitHub query list, deduplicated."""
        seen: set[str] = set()
        result: list[SearchQuery] = []
        for gen in (
            self.filename_queries,
            self.content_queries,
            self.path_queries,
            self.combined_queries,
            self.extension_queries,
        ):
            for q in gen():
                if q.query not in seen:
                    seen.add(q.query)
                    result.append(q)
        return result
