"""Tests for ai_finder.scanner module."""

import pytest

from ai_finder.scanner import SecretScanner, SecretMatch


class TestSecretMatch:
    def test_redacted_short_string(self):
        m = SecretMatch(rule_name="test", matched_text="abc")
        assert m.redacted() == "****"

    def test_redacted_long_string(self):
        m = SecretMatch(rule_name="test", matched_text="sk-abcdefghijklmnopqrstuvwxyz")
        redacted = m.redacted()
        assert "****" in redacted
        assert redacted.startswith("sk-a")
        assert redacted.endswith("wxyz")


class TestSecretScanner:
    def setup_method(self):
        self.scanner = SecretScanner()

    # --- OpenAI key ---

    def test_detects_openai_api_key(self):
        content = 'api_key = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"'
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "openai_api_key" in rules

    # --- Anthropic key ---

    def test_detects_anthropic_key(self):
        content = "ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "anthropic_api_key" in rules

    # --- GitHub token ---

    def test_detects_github_token(self):
        content = "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "github_token" in rules

    # --- AWS key ---

    def test_detects_aws_access_key(self):
        content = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "aws_access_key" in rules

    # --- Google API key ---

    def test_detects_google_api_key(self):
        content = "GOOGLE_KEY=AIzaSyDCvp5MTKBAnZe1234567890abcdefghijk"
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "google_api_key" in rules

    # --- Placeholder ---

    def test_detects_placeholder(self):
        content = "api_key = {{OPENAI_API_KEY}}"
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "placeholder_leak" in rules

    # --- Clean content ---

    def test_clean_content_returns_empty(self):
        content = "# This is just a README\nNo secrets here."
        matches = self.scanner.scan(content)
        assert matches == []

    def test_has_secrets_true(self):
        content = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        assert self.scanner.has_secrets(content) is True

    def test_has_secrets_false(self):
        content = "Just a regular markdown file."
        assert self.scanner.has_secrets(content) is False

    # --- Report ---

    def test_report_structure(self):
        content = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        report = self.scanner.report(content, url="http://example.com")
        assert report["url"] == "http://example.com"
        assert report["has_secrets"] is True
        assert report["secret_count"] >= 1
        assert isinstance(report["findings"], list)
        for f in report["findings"]:
            assert "rule" in f
            assert "line" in f
            assert "redacted" in f
            assert "context" in f

    def test_report_empty_for_clean_content(self):
        report = self.scanner.report("clean content", url="http://x.com")
        assert report["has_secrets"] is False
        assert report["secret_count"] == 0
        assert report["findings"] == []

    def test_line_number_reported(self):
        content = "line 1\nsk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef\nline 3"
        matches = self.scanner.scan(content)
        openai_matches = [m for m in matches if m.rule_name == "openai_api_key"]
        assert openai_matches
        assert openai_matches[0].line_number == 2
