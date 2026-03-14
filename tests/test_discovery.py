"""Tests for ai_finder.discovery module."""

import pytest

from ai_finder.discovery import (
    GoogleDorkGenerator,
    GitHubQueryGenerator,
    SearchQuery,
    TARGET_FILENAMES,
    CONTENT_SIGNATURES,
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
