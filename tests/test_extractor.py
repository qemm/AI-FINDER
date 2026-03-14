"""Tests for ai_finder.extractor module."""

import hashlib
import pytest

from ai_finder.extractor import FileExtractor, ExtractedFile, github_html_to_raw


class TestGithubHtmlToRaw:
    def test_blob_url_converted(self):
        url = "https://github.com/user/repo/blob/main/CLAUDE.md"
        expected = "https://raw.githubusercontent.com/user/repo/main/CLAUDE.md"
        assert github_html_to_raw(url) == expected

    def test_raw_url_unchanged(self):
        url = "https://raw.githubusercontent.com/user/repo/main/CLAUDE.md"
        assert github_html_to_raw(url) == url

    def test_non_github_url_unchanged(self):
        url = "https://example.com/some/path"
        assert github_html_to_raw(url) == url

    def test_github_url_without_blob_unchanged(self):
        url = "https://github.com/user/repo"
        assert github_html_to_raw(url) == url

    def test_nested_path_preserved(self):
        url = "https://github.com/user/repo/blob/main/dir/sub/AGENTS.md"
        result = github_html_to_raw(url)
        assert "dir/sub/AGENTS.md" in result
        assert result.startswith("https://raw.githubusercontent.com/")


class TestExtractedFile:
    def test_is_valid_with_content(self):
        ef = ExtractedFile(url="http://x.com", raw_content="hello", content_hash="abc")
        assert ef.is_valid is True

    def test_is_valid_false_when_error(self):
        ef = ExtractedFile(
            url="http://x.com", raw_content="hello", content_hash="abc", error="timeout"
        )
        assert ef.is_valid is False

    def test_is_valid_false_when_empty_content(self):
        ef = ExtractedFile(url="http://x.com", raw_content="", content_hash="")
        assert ef.is_valid is False


class TestFileExtractorStaticHelpers:
    def test_extract_system_prompts_you_are(self):
        text = "You are an expert developer assistant.\nSome other text."
        blocks = FileExtractor._extract_system_prompts(text)
        assert any("You are" in b for b in blocks)

    def test_extract_system_prompts_section_header(self):
        text = "## Instructions\nAlways respond in English.\n## Other"
        blocks = FileExtractor._extract_system_prompts(text)
        assert any("Instructions" in b or "Always respond" in b for b in blocks)

    def test_extract_system_prompts_xml_tag(self):
        text = "<system>You are a helpful assistant.</system>"
        blocks = FileExtractor._extract_system_prompts(text)
        # Either regex or BS4 should pick it up
        combined = " ".join(blocks)
        assert "assistant" in combined.lower() or "system" in combined.lower()

    def test_extract_system_prompts_empty_text(self):
        blocks = FileExtractor._extract_system_prompts("")
        assert blocks == []

    def test_extract_system_prompts_deduplicates(self):
        text = "You are an expert.\nYou are an expert."
        blocks = FileExtractor._extract_system_prompts(text)
        # Should not contain duplicates
        assert len(blocks) == len(set(blocks))
