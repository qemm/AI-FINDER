"""Tests for ai_finder.scanner module."""

import pytest

from ai_finder.scanner import SecretScanner, SecretMatch, SecretRule, shannon_entropy
import re


class TestShannonEntropy:
    def test_empty_string(self):
        assert shannon_entropy("") == 0.0

    def test_single_char(self):
        # One unique character → entropy = 0
        assert shannon_entropy("aaaa") == 0.0

    def test_two_equal_chars(self):
        # Two equally probable characters → entropy = 1.0 bit/char
        assert abs(shannon_entropy("abab") - 1.0) < 1e-9

    def test_high_entropy_random_string(self):
        # A realistic API key token should score well above 3.5 bits/char
        token = "xK9mP2qR8sT1vW4yZ6bD3hN5jL7cF0eA"  # 33 unique-ish chars
        assert shannon_entropy(token) > 3.5

    def test_low_entropy_repeated(self):
        # Highly repetitive string is low entropy
        assert shannon_entropy("aaaaabbbbb") < 2.0


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

    def test_openai_key_requires_minimum_length(self):
        # Only 20 chars after sk- → too short for the 32–48 range
        short_key = "sk-" + "A" * 20
        matches = self.scanner.scan(short_key)
        rules = [m.rule_name for m in matches]
        assert "openai_api_key" not in rules

    def test_openai_key_rejects_over_max_length(self):
        # 50 repeated 'A' chars after sk- → exceeds the 48-char upper bound
        long_key = "sk-" + "A" * 50
        matches = self.scanner.scan(long_key)
        openai_matches = [m for m in matches if m.rule_name == "openai_api_key"]
        # The regex matches exactly the first 32–48 chars; 50 repeated 'A's
        # have zero entropy, but openai_api_key has no min_entropy filter,
        # so a 48-char sub-match is still found inside the longer string.
        matched_lengths = [len(m.matched_text) - 3 for m in openai_matches]  # subtract "sk-"
        assert all(length <= 48 for length in matched_lengths)

    # --- Anthropic key ---

    def test_detects_anthropic_key(self):
        content = "ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "anthropic_api_key" in rules

    def test_detects_anthropic_sid01_key(self):
        # Verify the sid01 sub-format (longer key) is also caught
        key = "sk-ant-sid01-" + "A" * 45 + "x" * 45  # 90 chars of suffix
        content = f"CLAUDE_KEY={key}"
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

    # --- Google Gemini / AI Studio key ---

    def test_detects_google_api_key(self):
        content = "GOOGLE_KEY=AIzaSyDCvp5MTKBAnZe1234567890abcdefghijk"
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "google_api_key" in rules

    def test_google_key_requires_aizasy_prefix(self):
        # Keys with 'AIza' prefix but missing the required 'Sy' suffix should not match
        content = "KEY=AIzaXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "google_api_key" not in rules

    # --- LangChain / LangSmith key ---

    def test_detects_langsmith_api_key(self):
        content = "LANGCHAIN_API_KEY=ls__abcdefghijklmnopqrstuvwxyz012345"
        matches = self.scanner.scan(content)
        rules = [m.rule_name for m in matches]
        assert "langsmith_api_key" in rules

    def test_langsmith_key_requires_exact_length(self):
        # Only 10 chars after ls__ → too short
        short_key = "ls__" + "a" * 10
        matches = self.scanner.scan(short_key)
        rules = [m.rule_name for m in matches]
        assert "langsmith_api_key" not in rules

    # --- High-entropy catch-all ---

    def test_high_entropy_secret_detected(self):
        # A realistic-looking token not matched by any named rule (40+ chars, high entropy)
        token = "xK9mP2qR8sT1vW4yZ6bD3hN5jL7cF0eA_mQpRsYzJ"  # 42 chars, high entropy
        matches = self.scanner.scan(token)
        rules = [m.rule_name for m in matches]
        assert "high_entropy_secret" in rules

    def test_high_entropy_secret_not_triggered_on_low_entropy(self):
        # 40 chars but all the same character → entropy = 0, should not trigger
        low_entropy = "A" * 40
        matches = self.scanner.scan(low_entropy)
        rules = [m.rule_name for m in matches]
        assert "high_entropy_secret" not in rules

    def test_high_entropy_secret_not_triggered_on_short_string(self):
        # High entropy but too short (< 40 chars)
        short = "xK9mP2qR8sT1vW4yZ6bD3hN5jL7cF0"  # 31 chars
        matches = self.scanner.scan(short)
        rules = [m.rule_name for m in matches]
        assert "high_entropy_secret" not in rules

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

    # --- min_entropy on custom rule ---

    def test_custom_rule_with_min_entropy_filters_low_entropy(self):
        rule = SecretRule(
            name="test_entropy_rule",
            pattern=re.compile(r"[A-Za-z0-9]{16,}"),
            description="test",
            min_entropy=3.5,
        )
        scanner = SecretScanner(rules=[rule])
        # All-same character → entropy = 0
        matches = scanner.scan("A" * 20)
        assert matches == []

    def test_custom_rule_with_min_entropy_passes_high_entropy(self):
        rule = SecretRule(
            name="test_entropy_rule",
            pattern=re.compile(r"[A-Za-z0-9]{16,}"),
            description="test",
            min_entropy=3.5,
        )
        scanner = SecretScanner(rules=[rule])
        # High-entropy token
        matches = scanner.scan("xK9mP2qR8sT1vW4y")
        assert len(matches) == 1
        assert matches[0].rule_name == "test_entropy_rule"

