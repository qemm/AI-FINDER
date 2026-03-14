"""
discovery.py — Search-query / dork generation module.

Produces:
  - Google dork strings targeting AI agent config files.
  - GitHub Code Search API query strings.
  - GitLab Search API query strings.
  - S3 bucket discovery dorks.
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

#: S3-specific search terms for exposed AI configuration files.
S3_DORK_TERMS: list[str] = [
    "CLAUDE.md",
    "AGENTS.md",
    ".cursorrules",
    "system_prompt",
    "agent_config",
    "openai_config",
    "langchain_config",
    "crewai_config",
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


# ---------------------------------------------------------------------------
# GitLab search query generator
# ---------------------------------------------------------------------------


class GitLabQueryGenerator:
    """Generates GitLab Search API query strings.

    Reference: https://docs.gitlab.com/ee/api/search.html
    Uses the ``blobs`` scope to search file contents across all public projects.
    """

    def filename_queries(self) -> Iterator[SearchQuery]:
        """One query per target filename (basename only)."""
        for fname in TARGET_FILENAMES:
            basename = fname.split("/")[-1]
            yield SearchQuery(
                platform="gitlab",
                query=basename,
                description=f"GitLab blob search for filename: {basename}",
                tags=["filename", basename],
            )

    def content_queries(self) -> Iterator[SearchQuery]:
        """One query per content signature."""
        for sig in CONTENT_SIGNATURES:
            yield SearchQuery(
                platform="gitlab",
                query=sig,
                description=f"GitLab blob search for content: {sig!r}",
                tags=["content-signature"],
            )

    def all_queries(self) -> list[SearchQuery]:
        """Return full GitLab query list, deduplicated."""
        seen: set[str] = set()
        result: list[SearchQuery] = []
        for gen in (self.filename_queries, self.content_queries):
            for q in gen():
                if q.query not in seen:
                    seen.add(q.query)
                    result.append(q)
        return result


# ---------------------------------------------------------------------------
# S3 bucket dork generator
# ---------------------------------------------------------------------------


class S3DorkGenerator:
    """Generates Google dorks and search patterns to discover exposed S3
    buckets that contain AI agent configuration files.

    Typical exposure vectors:
    - Open S3 buckets indexed by search engines.
    - S3 bucket listings linked from GitHub READMEs.
    - AWS bucket names leaked in source code or CI configs.
    """

    _S3_LISTING_TMPL = 'site:s3.amazonaws.com "{term}"'
    _S3_CUSTOM_DOMAIN_TMPL = 'site:*.s3.amazonaws.com "{term}"'
    _S3_BUCKET_GITHUB_TMPL = 's3.amazonaws.com "{term}" site:github.com'

    def s3_listing_dorks(self) -> Iterator[SearchQuery]:
        """Dorks targeting open S3 bucket directory listings."""
        for term in S3_DORK_TERMS:
            yield SearchQuery(
                platform="google",
                query=self._S3_LISTING_TMPL.format(term=term),
                description=f"S3 public listing containing: {term}",
                tags=["s3", "listing"],
            )

    def s3_custom_domain_dorks(self) -> Iterator[SearchQuery]:
        """Dorks targeting custom-domain S3 buckets."""
        for term in S3_DORK_TERMS:
            yield SearchQuery(
                platform="google",
                query=self._S3_CUSTOM_DOMAIN_TMPL.format(term=term),
                description=f"S3 custom domain containing: {term}",
                tags=["s3", "custom-domain"],
            )

    def s3_github_leak_dorks(self) -> Iterator[SearchQuery]:
        """Dorks for S3 bucket URLs leaked in GitHub repositories."""
        for term in S3_DORK_TERMS:
            yield SearchQuery(
                platform="google",
                query=self._S3_BUCKET_GITHUB_TMPL.format(term=term),
                description=f"S3 URL leaked in GitHub for: {term}",
                tags=["s3", "github-leak"],
            )

    def all_dorks(self) -> list[SearchQuery]:
        """Return full S3 dork list, deduplicated."""
        seen: set[str] = set()
        result: list[SearchQuery] = []
        for gen in (
            self.s3_listing_dorks,
            self.s3_custom_domain_dorks,
            self.s3_github_leak_dorks,
        ):
            for q in gen():
                if q.query not in seen:
                    seen.add(q.query)
                    result.append(q)
        return result
