"""
scanner.py — Secret / API-key leak detection module.

Scans file content for:
  - Hardcoded API keys (OpenAI, Anthropic, GitHub, AWS, …)
  - Placeholder patterns that were accidentally replaced with real values
  - Generic high-entropy token patterns (Shannon-entropy based)
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Entropy utilities
# ---------------------------------------------------------------------------


def shannon_entropy(data: str) -> float:
    """Return the Shannon entropy of *data* in bits per character.

    A perfectly random string of *n* unique characters has entropy
    ``log2(n)`` (e.g. ~5.17 for base-62 alphanumeric).  Dictionary
    words or sequential patterns score much lower (≈2–3 bits/char).
    """
    if not data:
        return 0.0
    freq = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())

# ---------------------------------------------------------------------------
# Secret detection patterns
# ---------------------------------------------------------------------------

@dataclass
class SecretMatch:
    """A single detected secret/leak."""

    rule_name: str
    matched_text: str          # The matched string (may be redacted in output)
    line_number: Optional[int] = None
    context: str = ""          # Surrounding text snippet

    def redacted(self) -> str:
        """Return a safe representation with most of the secret hidden."""
        if len(self.matched_text) <= 8:
            return "****"
        return self.matched_text[:4] + "****" + self.matched_text[-4:]


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

@dataclass
class SecretRule:
    name: str
    pattern: re.Pattern[str]
    description: str
    min_entropy: float = 0.0  # if > 0, matched text must meet this entropy threshold


_SECRET_RULES: list[SecretRule] = [
    SecretRule(
        name="openai_api_key",
        pattern=re.compile(r'sk-[A-Za-z0-9]{32,48}'),
        description="OpenAI API key (sk-... with 32–48 alphanumeric chars)",
    ),
    SecretRule(
        name="anthropic_api_key",
        pattern=re.compile(r'sk-ant-[A-Za-z0-9\-_]{20,}', re.IGNORECASE),
        description="Anthropic / Claude API key (sk-ant-... e.g. sk-ant-sid01-...)",
    ),
    SecretRule(
        name="github_token",
        pattern=re.compile(r'gh[pousr]_[A-Za-z0-9]{36,}', re.IGNORECASE),
        description="GitHub personal access token",
    ),
    SecretRule(
        name="aws_access_key",
        pattern=re.compile(r'AKIA[A-Z0-9]{16}', re.IGNORECASE),
        description="AWS Access Key ID",
    ),
    SecretRule(
        name="aws_secret_key",
        pattern=re.compile(r'(?:aws[_\-]?secret[_\-]?(?:access[_\-]?)?key)\s*[=:]\s*["\']?[A-Za-z0-9/+=]{40}["\']?', re.IGNORECASE),
        description="AWS Secret Access Key",
    ),
    SecretRule(
        name="google_api_key",
        pattern=re.compile(r'AIzaSy[A-Za-z0-9\-_]{33}'),
        description="Google Gemini / AI Studio API key (AIzaSy...)",
    ),
    SecretRule(
        name="huggingface_token",
        pattern=re.compile(r'hf_[A-Za-z0-9]{34,}', re.IGNORECASE),
        description="HuggingFace API token (hf_...)",
    ),
    SecretRule(
        name="langsmith_api_key",
        pattern=re.compile(r'ls__[A-Za-z0-9]{32}'),
        description="LangChain / LangSmith API key (ls__...)",
    ),
    SecretRule(
        name="hardcoded_api_key_assignment",
        pattern=re.compile(
            r'(?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|auth[_\-]?token)'
            r'\s*[=:]\s*["\']([A-Za-z0-9\-_\.]{16,})["\']',
            re.IGNORECASE,
        ),
        description="Generic API key / token assignment",
    ),
    SecretRule(
        name="placeholder_leak",
        pattern=re.compile(
            r'\{\{\s*(?:OPENAI|ANTHROPIC|CLAUDE|GITHUB|AWS|GOOGLE|HF)[_A-Z]*\s*\}\}',
            re.IGNORECASE,
        ),
        description="Unfilled secret placeholder (e.g. {{OPENAI_API_KEY}})",
    ),
    SecretRule(
        name="env_var_exposure",
        pattern=re.compile(
            r'(?:os\.environ|getenv|process\.env)\s*[\[\(]["\']'
            r'([A-Z_]{5,}(?:KEY|TOKEN|SECRET|PASSWORD|API)[A-Z_]*)["\']',
            re.IGNORECASE,
        ),
        description="Environment variable exposure of sensitive key name",
    ),
    SecretRule(
        name="high_entropy_secret",
        pattern=re.compile(r'[A-Za-z0-9+/=\-_]{40,}'),
        description="High-entropy token (possible undeclared API key or secret)",
        min_entropy=3.5,
    ),
]


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class SecretScanner:
    """Scan raw file content for leaked secrets or sensitive patterns."""

    def __init__(self, rules: Optional[list[SecretRule]] = None) -> None:
        self._rules = rules if rules is not None else _SECRET_RULES

    def scan(self, content: str, url: str = "") -> list[SecretMatch]:
        """Return all :class:`SecretMatch` objects found in *content*."""
        matches: list[SecretMatch] = []
        lines = content.splitlines()

        for rule in self._rules:
            for line_no, line in enumerate(lines, start=1):
                for m in rule.pattern.finditer(line):
                    # Entropy-based filter: skip low-randomness matches
                    if rule.min_entropy > 0 and shannon_entropy(m.group(0)) < rule.min_entropy:
                        continue

                    # Build a small context snippet (avoid capturing the full secret)
                    start = max(0, m.start() - 20)
                    end = min(len(line), m.end() + 20)
                    context = line[start:end]

                    matches.append(
                        SecretMatch(
                            rule_name=rule.name,
                            matched_text=m.group(0),
                            line_number=line_no,
                            context=context,
                        )
                    )

        return matches

    def has_secrets(self, content: str) -> bool:
        """Quick boolean check."""
        return bool(self.scan(content))

    def report(self, content: str, url: str = "") -> dict:
        """Return a structured report dict suitable for storage."""
        found = self.scan(content, url)
        return {
            "url": url,
            "secret_count": len(found),
            "has_secrets": bool(found),
            "findings": [
                {
                    "rule": s.rule_name,
                    "line": s.line_number,
                    "redacted": s.redacted(),
                    "context": s.context,
                }
                for s in found
            ],
        }
