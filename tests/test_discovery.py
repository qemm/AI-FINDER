"""Tests for ai_finder.discovery module."""

import pytest

from ai_finder.discovery import (
    GoogleDorkGenerator,
    WebDorkGenerator,
    GitHubQueryGenerator,
    GitLabQueryGenerator,
    S3DorkGenerator,
    SearchQuery,
    TARGET_FILENAMES,
    CONTENT_SIGNATURES,
    TARGET_PATHS,
    S3_DORK_TERMS,
    GITHUB_RAW_BASE,
    GITLAB_RAW_BASE,
    COMMON_BRANCHES,
    build_github_raw_urls,
    build_gitlab_raw_urls,
)


class TestSearchQuery:
    def test_str_returns_query(self):
        q = SearchQuery(platform="google", query="intitle:CLAUDE.md site:github.com")
        assert str(q) == "intitle:CLAUDE.md site:github.com"

    def test_default_tags_empty(self):
        q = SearchQuery(platform="github", query="filename:CLAUDE.md")
        assert q.tags == []


class TestGoogleDorkGenerator:
    def setup_method(self):
        self.gen = GoogleDorkGenerator()

    def test_filename_dorks_returns_queries(self):
        dorks = list(self.gen.filename_dorks())
        assert len(dorks) == len(TARGET_FILENAMES)
        for d in dorks:
            assert d.platform == "google"
            assert "site:github.com" in d.query

    def test_content_dorks_returns_queries(self):
        dorks = list(self.gen.content_dorks())
        assert len(dorks) == len(CONTENT_SIGNATURES)
        for d in dorks:
            assert "filetype:" in d.query

    def test_path_dorks_returns_queries(self):
        dorks = list(self.gen.path_dorks())
        assert all(d.platform == "google" for d in dorks)

    def test_combined_dorks_cross_product(self):
        dorks = list(self.gen.combined_dorks())
        assert len(dorks) == 9  # 3 files × 3 signatures

    def test_all_dorks_are_unique(self):
        dorks = self.gen.all_dorks()
        queries = [d.query for d in dorks]
        assert len(queries) == len(set(queries)), "Duplicate dork found"

    def test_all_dorks_non_empty(self):
        assert len(self.gen.all_dorks()) > 0

    def test_claude_md_in_filename_dorks(self):
        dorks = list(self.gen.filename_dorks())
        claude_dorks = [d for d in dorks if "CLAUDE.md" in d.query]
        assert claude_dorks, "Expected at least one CLAUDE.md dork"

    def test_cursorrules_in_filename_dorks(self):
        dorks = list(self.gen.filename_dorks())
        cursor_dorks = [d for d in dorks if ".cursorrules" in d.query]
        assert cursor_dorks


class TestGitHubQueryGenerator:
    def setup_method(self):
        self.gen = GitHubQueryGenerator()

    def test_filename_queries_use_basename(self):
        queries = list(self.gen.filename_queries())
        for q in queries:
            assert q.platform == "github"
            assert q.query.startswith("filename:")
            # No path separators in filename: value
            fname_part = q.query.split("filename:")[1]
            assert "/" not in fname_part

    def test_content_queries_are_quoted(self):
        queries = list(self.gen.content_queries())
        for q in queries:
            assert '"' in q.query

    def test_combined_queries_have_filename_and_content(self):
        queries = list(self.gen.combined_queries())
        for q in queries:
            assert "filename:" in q.query
            assert '"' in q.query

    def test_all_queries_unique(self):
        queries = self.gen.all_queries()
        raw = [q.query for q in queries]
        assert len(raw) == len(set(raw))

    def test_all_queries_non_empty(self):
        assert len(self.gen.all_queries()) > 0


class TestGitLabQueryGenerator:
    def setup_method(self):
        self.gen = GitLabQueryGenerator()

    def test_filename_queries_platform(self):
        queries = list(self.gen.filename_queries())
        assert len(queries) == len(TARGET_FILENAMES)
        for q in queries:
            assert q.platform == "gitlab"

    def test_filename_queries_use_basename(self):
        queries = list(self.gen.filename_queries())
        for q in queries:
            # Query should be a bare filename (basename only)
            assert "/" not in q.query

    def test_content_queries_returned(self):
        queries = list(self.gen.content_queries())
        assert len(queries) == len(CONTENT_SIGNATURES)
        for q in queries:
            assert q.platform == "gitlab"

    def test_all_queries_unique(self):
        queries = self.gen.all_queries()
        raw = [q.query for q in queries]
        assert len(raw) == len(set(raw))

    def test_all_queries_non_empty(self):
        assert len(self.gen.all_queries()) > 0

    def test_claude_md_in_queries(self):
        queries = list(self.gen.filename_queries())
        assert any("CLAUDE.md" in q.query for q in queries)


class TestS3DorkGenerator:
    def setup_method(self):
        self.gen = S3DorkGenerator()

    def test_s3_listing_dorks_platform(self):
        dorks = list(self.gen.s3_listing_dorks())
        assert len(dorks) == len(S3_DORK_TERMS)
        for d in dorks:
            assert d.platform == "google"
            # Dork format: site:s3.amazonaws.com "<term>"
            assert d.query.startswith("site:s3.amazonaws.com ")

    def test_s3_custom_domain_dorks(self):
        dorks = list(self.gen.s3_custom_domain_dorks())
        assert len(dorks) == len(S3_DORK_TERMS)
        for d in dorks:
            # Dork format: site:*.s3.amazonaws.com "<term>"
            assert d.query.startswith("site:*.s3.amazonaws.com ")

    def test_s3_github_leak_dorks(self):
        dorks = list(self.gen.s3_github_leak_dorks())
        assert len(dorks) == len(S3_DORK_TERMS)
        for d in dorks:
            # Dork format: s3.amazonaws.com "<term>" site:github.com
            assert d.query.startswith("s3.amazonaws.com ")
            assert d.query.endswith("site:github.com")

    def test_all_dorks_unique(self):
        dorks = self.gen.all_dorks()
        queries = [d.query for d in dorks]
        assert len(queries) == len(set(queries))

    def test_all_dorks_non_empty(self):
        assert len(self.gen.all_dorks()) > 0

    def test_all_dorks_cover_all_terms(self):
        dorks = self.gen.all_dorks()
        dork_text = " ".join(d.query for d in dorks)
        for term in S3_DORK_TERMS:
            assert term in dork_text, f"S3 term {term!r} not found in any dork"


# ---------------------------------------------------------------------------
# Constants: GITHUB_RAW_BASE, GITLAB_RAW_BASE, COMMON_BRANCHES
# ---------------------------------------------------------------------------


class TestBruteForceConstants:
    def test_github_raw_base_is_string(self):
        assert isinstance(GITHUB_RAW_BASE, str)
        assert GITHUB_RAW_BASE.startswith("https://")

    def test_gitlab_raw_base_is_string(self):
        assert isinstance(GITLAB_RAW_BASE, str)
        assert GITLAB_RAW_BASE.startswith("https://")

    def test_common_branches_non_empty(self):
        assert len(COMMON_BRANCHES) > 0

    def test_common_branches_includes_main_and_master(self):
        assert "main" in COMMON_BRANCHES
        assert "master" in COMMON_BRANCHES


# ---------------------------------------------------------------------------
# build_github_raw_urls
# ---------------------------------------------------------------------------


class TestBuildGithubRawUrls:
    def test_returns_urls_for_all_branches_and_filenames(self):
        urls = build_github_raw_urls("owner", "repo")
        # Should have one URL per branch per filename
        assert len(urls) == len(COMMON_BRANCHES) * len(TARGET_FILENAMES)

    def test_urls_use_correct_base(self):
        urls = build_github_raw_urls("owner", "repo")
        for url in urls:
            assert url.startswith(GITHUB_RAW_BASE)

    def test_url_format_is_correct(self):
        urls = build_github_raw_urls("myorg", "myrepo", branches=["main"])
        for url in urls:
            assert url.startswith("https://raw.githubusercontent.com/myorg/myrepo/main/")

    def test_config_filename_is_last_component(self):
        urls = build_github_raw_urls("owner", "repo", branches=["main"])
        for url in urls:
            last = url.rsplit("/", 1)[-1]
            # The last component must be one of the target filenames (basename)
            assert any(url.endswith(f) for f in TARGET_FILENAMES)

    def test_custom_branches_are_used(self):
        urls = build_github_raw_urls("owner", "repo", branches=["custom-branch"])
        assert all("/custom-branch/" in url for url in urls)

    def test_custom_paths_override_defaults(self):
        urls = build_github_raw_urls("owner", "repo", branches=["main"], paths=["CLAUDE.md"])
        assert len(urls) == 1
        assert urls[0] == "https://raw.githubusercontent.com/owner/repo/main/CLAUDE.md"

    def test_results_are_deduplicated(self):
        urls = build_github_raw_urls("owner", "repo")
        assert len(urls) == len(set(urls))

    def test_all_target_filenames_are_covered(self):
        urls = build_github_raw_urls("owner", "repo", branches=["main"])
        for fname in TARGET_FILENAMES:
            assert any(url.endswith(fname) for url in urls)

    def test_urls_include_subdirectory_paths_when_provided(self):
        urls = build_github_raw_urls(
            "owner", "repo",
            branches=["main"],
            paths=["agents/CLAUDE.md", "CLAUDE.md"],
        )
        assert "https://raw.githubusercontent.com/owner/repo/main/agents/CLAUDE.md" in urls
        assert "https://raw.githubusercontent.com/owner/repo/main/CLAUDE.md" in urls


# ---------------------------------------------------------------------------
# build_gitlab_raw_urls
# ---------------------------------------------------------------------------


class TestBuildGitlabRawUrls:
    def test_returns_urls_for_all_branches_and_filenames(self):
        urls = build_gitlab_raw_urls("group", "project")
        assert len(urls) == len(COMMON_BRANCHES) * len(TARGET_FILENAMES)

    def test_urls_use_correct_base(self):
        urls = build_gitlab_raw_urls("group", "project")
        for url in urls:
            assert url.startswith(GITLAB_RAW_BASE)

    def test_url_format_is_correct(self):
        urls = build_gitlab_raw_urls("mygroup", "myproject", branches=["main"])
        for url in urls:
            assert url.startswith(
                "https://gitlab.com/mygroup/myproject/-/raw/main/"
            )

    def test_config_filename_is_last_component(self):
        urls = build_gitlab_raw_urls("group", "project", branches=["main"])
        for url in urls:
            assert any(url.endswith(f) for f in TARGET_FILENAMES)

    def test_custom_branches_are_used(self):
        urls = build_gitlab_raw_urls("group", "project", branches=["feature"])
        assert all("/-/raw/feature/" in url for url in urls)

    def test_custom_paths_override_defaults(self):
        urls = build_gitlab_raw_urls(
            "group", "project", branches=["main"], paths=["AGENTS.md"]
        )
        assert len(urls) == 1
        assert urls[0] == "https://gitlab.com/group/project/-/raw/main/AGENTS.md"

    def test_results_are_deduplicated(self):
        urls = build_gitlab_raw_urls("group", "project")
        assert len(urls) == len(set(urls))

    def test_all_target_filenames_are_covered(self):
        urls = build_gitlab_raw_urls("group", "project", branches=["main"])
        for fname in TARGET_FILENAMES:
            assert any(url.endswith(fname) for url in urls)


# ---------------------------------------------------------------------------
# WebDorkGenerator — open-web (no site: restriction) dorks
# ---------------------------------------------------------------------------


class TestWebDorkGenerator:
    def setup_method(self):
        self.gen = WebDorkGenerator()

    # ---- filename_dorks ----

    def test_filename_dorks_count(self):
        dorks = list(self.gen.filename_dorks())
        assert len(dorks) == len(TARGET_FILENAMES)

    def test_filename_dorks_platform_is_web(self):
        for d in self.gen.filename_dorks():
            assert d.platform == "web"

    def test_filename_dorks_have_no_site_restriction(self):
        for d in self.gen.filename_dorks():
            assert "site:" not in d.query

    def test_filename_dork_uses_intitle(self):
        dorks = list(self.gen.filename_dorks())
        assert all(d.query.startswith('intitle:"') for d in dorks)

    def test_filename_dork_contains_fname(self):
        for fname in TARGET_FILENAMES:
            dorks = list(self.gen.filename_dorks())
            assert any(fname in d.query for d in dorks)

    # ---- content_dorks ----

    def test_content_dorks_count(self):
        dorks = list(self.gen.content_dorks())
        assert len(dorks) == len(CONTENT_SIGNATURES)

    def test_content_dorks_platform_is_web(self):
        for d in self.gen.content_dorks():
            assert d.platform == "web"

    def test_content_dorks_have_no_site_restriction(self):
        for d in self.gen.content_dorks():
            assert "site:" not in d.query

    def test_content_dorks_contain_filetype_operators(self):
        for d in self.gen.content_dorks():
            assert "filetype:" in d.query

    def test_content_dorks_contain_signature(self):
        for sig in CONTENT_SIGNATURES:
            dorks = list(self.gen.content_dorks())
            assert any(sig in d.query for d in dorks)

    # ---- path_dorks ----

    def test_path_dorks_count(self):
        dorks = list(self.gen.path_dorks())
        assert len(dorks) == len(TARGET_PATHS)

    def test_path_dorks_platform_is_web(self):
        for d in self.gen.path_dorks():
            assert d.platform == "web"

    def test_path_dorks_have_no_site_restriction(self):
        for d in self.gen.path_dorks():
            assert "site:" not in d.query

    def test_path_dorks_use_inurl(self):
        for d in self.gen.path_dorks():
            assert "inurl:" in d.query

    # ---- combined_dorks ----

    def test_combined_dorks_cross_product(self):
        dorks = list(self.gen.combined_dorks())
        assert len(dorks) == 9  # 3 files × 3 signatures

    def test_combined_dorks_have_no_site_restriction(self):
        for d in self.gen.combined_dorks():
            assert "site:" not in d.query

    def test_combined_dorks_platform_is_web(self):
        for d in self.gen.combined_dorks():
            assert d.platform == "web"

    # ---- all_dorks ----

    def test_all_dorks_non_empty(self):
        assert len(self.gen.all_dorks()) > 0

    def test_all_dorks_are_unique(self):
        dorks = self.gen.all_dorks()
        queries = [d.query for d in dorks]
        assert len(queries) == len(set(queries))

    def test_all_dorks_open_web_tag(self):
        for d in self.gen.all_dorks():
            assert "open-web" in d.tags

    # ---- compare with GoogleDorkGenerator ----

    def test_web_dorks_are_distinct_from_github_dorks(self):
        github_queries = {d.query for d in GoogleDorkGenerator().all_dorks()}
        web_queries = {d.query for d in WebDorkGenerator().all_dorks()}
        # No web dork should be identical to any github-targeted dork
        assert github_queries.isdisjoint(web_queries), (
            "WebDorkGenerator produced queries that overlap with "
            "GoogleDorkGenerator — web dorks must not have site: restrictions"
        )

    def test_web_dorks_cover_same_filenames_as_google_dorks(self):
        """Every filename covered by GoogleDorkGenerator is also covered."""
        for fname in TARGET_FILENAMES:
            web_dorks = list(self.gen.filename_dorks())
            assert any(fname in d.query for d in web_dorks)
