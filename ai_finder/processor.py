"""
processor.py — Platform categorisation + "Model DNA" classification.

Given an :class:`~ai_finder.extractor.ExtractedFile`, this module:
  1. Detects the AI platform (Claude, OpenAI, Cursor, …).
  2. Extracts "Model DNA" traits: persona, tech stack, ethical constraints.
  3. Returns an enriched :class:`ProcessedFile`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ai_finder.extractor import ExtractedFile

# ---------------------------------------------------------------------------
# Platform detection rules
# ---------------------------------------------------------------------------

# Each entry: (platform_label, list_of_regex_patterns)
_PLATFORM_RULES: list[tuple[str, list[str]]] = [
    (
        "claude",
        [
            r"anthropic",
            r"claude",
            r"Assistant is a large language model trained by Anthropic",
            r"claude\.ai",
            r"CLAUDE\.md",
        ],
    ),
    (
        "openai",
        [
            r"openai",
            r"gpt-?[34]",
            r"chatgpt",
            r"openai\.api_key",
            r"OPENAI_API_KEY",
            r"gpt-4o",
        ],
    ),
    (
        "cursor",
        [
            r"\.cursorrules",
            r"cursor\s*rules",
            r"cursorai",
            r"cursor\.sh",
        ],
    ),
    (
        "copilot",
        [
            r"github\s*copilot",
            r"copilot-instructions",
            r"copilot\.md",
        ],
    ),
    (
        "langchain",
        [
            r"langchain",
            r"from langchain",
            r"import langchain",
            r"LLMChain",
            r"AgentExecutor",
        ],
    ),
    (
        "crewai",
        [
            r"crewai",
            r"from crewai",
            r"import crewai",
            r"CrewAI",
            r"crew\.kickoff",
        ],
    ),
    (
        "cline",
        [
            r"\.clinerules",
            r"cline",
        ],
    ),
    (
        "gemini",
        [
            r"gemini",
            r"google\.generativeai",
            r"bard",
        ],
    ),
]

# ---------------------------------------------------------------------------
# Model-DNA extraction patterns
# ---------------------------------------------------------------------------

# Persona extraction: first line starting with "You are …"
_PERSONA_RE = re.compile(
    r"(?:^|\n)(You are[^\n]{0,300})",
    re.IGNORECASE,
)

# Tech-stack hints
_TECH_STACK_KEYWORDS: list[str] = [
    "python",
    "typescript",
    "javascript",
    "rust",
    "go",
    "java",
    "react",
    "nextjs",
    "fastapi",
    "django",
    "flask",
    "langchain",
    "crewai",
    "llamaindex",
    "docker",
    "kubernetes",
    "aws",
    "gcp",
    "azure",
]

# Ethical/constraint markers
_CONSTRAINT_RE = re.compile(
    r"(?:do\s*not|never|avoid|must\s*not|refus[ei]|prohibit)[^\n.]{0,200}",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class ModelDNA:
    """Structured representation of inferred traits."""

    persona: Optional[str] = None
    tech_stack: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    raw_traits: dict = field(default_factory=dict)


@dataclass
class ProcessedFile:
    """Output of the processor, wrapping an :class:`ExtractedFile`."""

    source: ExtractedFile
    platform: str = "unknown"
    confidence: float = 0.0  # 0.0 – 1.0
    model_dna: ModelDNA = field(default_factory=ModelDNA)
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------


class FileProcessor:
    """Classify and enrich a single :class:`ExtractedFile`."""

    def process(self, extracted: ExtractedFile) -> ProcessedFile:
        text = extracted.raw_content.lower()
        original_text = extracted.raw_content

        platform, confidence = self._detect_platform(text, extracted.url)
        dna = self._extract_model_dna(original_text)
        tags = self._build_tags(platform, dna, extracted)

        result = ProcessedFile(
            source=extracted,
            platform=platform,
            confidence=confidence,
            model_dna=dna,
            tags=tags,
        )
        # Propagate back for storage convenience
        extracted.platform = platform
        extracted.tags = tags
        return result

    def process_many(self, files: list[ExtractedFile]) -> list[ProcessedFile]:
        return [self.process(f) for f in files if f.is_valid]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_platform(
        text_lower: str, url: str
    ) -> tuple[str, float]:
        """Return (platform_label, confidence_0_to_1)."""
        url_lower = url.lower()
        scores: dict[str, int] = {}

        for platform, patterns in _PLATFORM_RULES:
            count = 0
            for pat in patterns:
                if re.search(pat, text_lower, re.IGNORECASE) or re.search(
                    pat, url_lower, re.IGNORECASE
                ):
                    count += 1
            if count:
                scores[platform] = count

        if not scores:
            return "unknown", 0.0

        best_platform = max(scores, key=lambda k: scores[k])
        max_possible = max(len(rules) for _, rules in _PLATFORM_RULES)
        confidence = min(scores[best_platform] / max_possible, 1.0)
        return best_platform, round(confidence, 2)

    @staticmethod
    def _extract_model_dna(text: str) -> ModelDNA:
        # Persona
        persona: Optional[str] = None
        m = _PERSONA_RE.search(text)
        if m:
            persona = m.group(1).strip()[:200]

        # Tech stack
        text_lower = text.lower()
        tech_stack = [kw for kw in _TECH_STACK_KEYWORDS if kw in text_lower]

        # Ethical constraints
        constraints = [
            m.group(0).strip()[:150]
            for m in _CONSTRAINT_RE.finditer(text)
        ]

        return ModelDNA(
            persona=persona,
            tech_stack=tech_stack,
            constraints=constraints,
            raw_traits={
                "persona_found": persona is not None,
                "tech_stack_count": len(tech_stack),
                "constraint_count": len(constraints),
            },
        )

    @staticmethod
    def _build_tags(
        platform: str, dna: ModelDNA, extracted: ExtractedFile
    ) -> list[str]:
        tags: set[str] = {platform}
        tags.update(dna.tech_stack)
        if dna.persona:
            tags.add("has-persona")
        if dna.constraints:
            tags.add("has-constraints")
        if extracted.system_prompt_blocks:
            tags.add("has-system-prompt")
        return sorted(tags)
