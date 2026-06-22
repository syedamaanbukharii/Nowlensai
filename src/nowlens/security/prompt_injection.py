"""Prompt-injection mitigation.

Defence-in-depth, not a guarantee. We scan free-text user input for well-known
injection / jailbreak patterns and for attempts to extract the system prompt or
secrets. The chat path also passes retrieved *document* content through the same
scan, because indirect injection (instructions hidden in a crawled page) is the
more dangerous vector for a RAG system.

The scan is deterministic and unit-tested. A match raises
:class:`PromptInjectionError` only above a severity threshold so that benign
mentions (e.g. a doc that literally discusses "system prompts") are not blocked
outright — lower-severity hits are reported for logging/auditing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from nowlens.core.config import get_settings
from nowlens.core.exceptions import PromptInjectionError, ValidationError

# (category, weight, compiled pattern). Weights feed a simple severity score.
_PATTERNS: list[tuple[str, int, re.Pattern[str]]] = [
    (
        "instruction_override",
        3,
        re.compile(
            r"ignore\s+(all\s+|the\s+)?(previous|prior|above)\s+(instructions|prompts?)", re.I
        ),
    ),
    (
        "instruction_override",
        3,
        re.compile(r"disregard\s+(all\s+|the\s+)?(previous|prior|above|system)", re.I),
    ),
    ("role_hijack", 3, re.compile(r"you\s+are\s+now\s+(a|an|the)\b", re.I)),
    (
        "role_hijack",
        2,
        re.compile(
            r"\bact\s+as\s+(if\s+you\s+are\s+)?(a\s+)?(dan|developer\s+mode|jailbroken)", re.I
        ),
    ),
    (
        "system_prompt_exfil",
        3,
        re.compile(
            r"(reveal|show|print|repeat|leak)\s+(me\s+)?(your\s+)?(system\s+prompt|initial\s+instructions|hidden\s+prompt)",
            re.I,
        ),
    ),
    (
        "secret_exfil",
        3,
        re.compile(
            r"(reveal|show|print|dump|leak|exfiltrate)\s+(the\s+)?(api[_\s-]?key|secret|password|token|credentials)",
            re.I,
        ),
    ),
    ("override_persona", 2, re.compile(r"\bdeveloper\s+mode\b", re.I)),
    ("override_persona", 2, re.compile(r"\bdo\s+anything\s+now\b", re.I)),
    ("delimiter_attack", 1, re.compile(r"(```|</?(system|assistant|user)>)", re.I)),
    (
        "override_refusals",
        2,
        re.compile(
            r"(bypass|ignore|disable)\s+(your\s+)?(safety|guardrails|content\s+policy|filters?)",
            re.I,
        ),
    ),
]

# Severity at/above which we hard-block.
_BLOCK_THRESHOLD = 3


@dataclass
class InjectionAssessment:
    flagged: bool
    severity: int
    categories: list[str] = field(default_factory=list)

    @property
    def should_block(self) -> bool:
        return self.severity >= _BLOCK_THRESHOLD


def scan(text: str) -> InjectionAssessment:
    """Return an assessment of injection risk for ``text`` (no exceptions)."""

    categories: list[str] = []
    severity = 0
    for category, weight, pattern in _PATTERNS:
        if pattern.search(text):
            categories.append(category)
            severity = max(severity, weight)
    # De-duplicate while preserving order.
    unique = list(dict.fromkeys(categories))
    return InjectionAssessment(flagged=bool(unique), severity=severity, categories=unique)


def guard_user_input(text: str) -> None:
    """Validate length + block high-severity injection attempts in user input."""

    max_chars = get_settings().security.max_input_chars
    if len(text) > max_chars:
        raise ValidationError(f"Input exceeds maximum length of {max_chars} characters")
    assessment = scan(text)
    if assessment.should_block:
        raise PromptInjectionError(
            "Input rejected: potential prompt-injection detected "
            f"({', '.join(assessment.categories)})"
        )


def scan_retrieved_context(text: str) -> InjectionAssessment:
    """Scan retrieved document content for indirect injection (report-only).

    Callers (the chat orchestrator) log/annotate this rather than blocking,
    since retrieved content is data — but a high score is a strong signal to
    treat that passage with suspicion.
    """

    return scan(text)
