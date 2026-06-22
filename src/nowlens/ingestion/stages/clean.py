"""Clean stage.

Two complementary cleaners:

* :func:`rule_clean` — deterministic, fast, dependency-free. Removes navigation
  boilerplate, collapses whitespace, drops repeated/near-empty lines, and
  normalises bullets. Always runs.
* :class:`AICleaner` — optional LLM pass that removes residual navigation noise,
  repairs broken formatting, and yields retrieval-friendly prose **while
  preserving fenced code blocks verbatim**. Enabled via
  ``NOWLENS_INGEST_AI_CLEANING``. On any provider error it degrades gracefully to
  the rule-cleaned text, so ingestion never fails because of the LLM.
"""

from __future__ import annotations

import re

from nowlens.core.logging import get_logger
from nowlens.llm.base import ChatMessage, LLMProvider

log = get_logger(__name__)

# Lines that are almost always navigation/chrome rather than content.
_NAV_PATTERNS = [
    re.compile(r"^\s*(skip to (main )?content|table of contents|on this page)\s*$", re.I),
    re.compile(r"^\s*(previous|next|back to top|edit this page|share this)\s*$", re.I),
    re.compile(r"^\s*(home\s*[>/]\s*).*", re.I),  # breadcrumbs
    re.compile(r"^\s*(copyright|©|all rights reserved).*", re.I),
    re.compile(r"^\s*(cookie|privacy policy|terms of (use|service)).*", re.I),
]
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def _is_nav_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in _NAV_PATTERNS)


def rule_clean(text: str) -> str:
    # Protect code fences from line-level filtering.
    placeholders: dict[str, str] = {}

    def _stash(match: re.Match[str]) -> str:
        key = f"\x00CODE{len(placeholders)}\x00"
        placeholders[key] = match.group(0)
        return key

    protected = _CODE_FENCE_RE.sub(_stash, text)

    cleaned_lines: list[str] = []
    previous = None
    for raw in protected.splitlines():
        line = _MULTISPACE_RE.sub(" ", raw.rstrip())
        if _is_nav_line(line):
            continue
        if line.strip() and line.strip() == (previous or "").strip():
            continue  # drop immediately repeated lines
        cleaned_lines.append(line)
        if line.strip():
            previous = line

    result = "\n".join(cleaned_lines)
    result = _MULTINEWLINE_RE.sub("\n\n", result).strip()

    for key, code in placeholders.items():
        result = result.replace(key, code)
    return result


_AI_CLEAN_SYSTEM = (
    "You clean scraped technical documentation for a retrieval system. "
    "Remove navigation menus, breadcrumbs, cookie/legal notices, and repeated "
    "boilerplate. Repair broken formatting and merge fragmented sentences. "
    "PRESERVE every fenced code block (```), command, table, and concrete "
    "example exactly as written — never summarise or alter them. Keep all "
    "technical facts. Return ONLY the cleaned document text with no preamble, "
    "commentary, or markdown fences around the whole output."
)


class AICleaner:
    """LLM-assisted cleaner. Falls back to the input text on any failure."""

    def __init__(self, provider: LLMProvider, *, max_chars: int = 6000) -> None:
        self._provider = provider
        self._max_chars = max_chars

    async def clean(self, text: str) -> str:
        # Guard against pathological inputs; the rule cleaner already ran.
        if len(text) > self._max_chars:
            # Clean the head deterministically and only AI-clean a bounded slice
            # to keep latency/cost predictable. The pipeline chunks afterwards.
            head, tail = text[: self._max_chars], text[self._max_chars :]
            cleaned_head = await self._clean_slice(head)
            return f"{cleaned_head}\n{tail}".strip()
        return await self._clean_slice(text)

    async def _clean_slice(self, text: str) -> str:
        if not text.strip():
            return text
        try:
            result = await self._provider.chat(
                [
                    ChatMessage("system", _AI_CLEAN_SYSTEM),
                    ChatMessage("user", text),
                ],
                temperature=0.0,
            )
            cleaned = result.content.strip()
            # Sanity: the model must not have collapsed the document to nothing.
            if len(cleaned) < max(40, len(text) // 5):
                log.warning("clean.ai_output_too_short", in_len=len(text), out_len=len(cleaned))
                return text
            return cleaned
        except Exception as exc:  # noqa: BLE001 - never fail ingestion on the LLM
            log.warning("clean.ai_failed", error=str(exc))
            return text
