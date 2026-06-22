"""Sanitisation helpers.

``nh3`` (Rust/ammonia bindings) performs HTML sanitisation. We expose a strict
HTML cleaner (for any content that will be rendered) and a plain-text stripper
(remove all markup), plus a control-character/whitespace cleaner for free-text
input.
"""

from __future__ import annotations

import unicodedata

import nh3

# Conservative allow-list for any rich text we choose to render.
_ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "code",
    "em",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
    "h1",
    "h2",
    "h3",
    "h4",
    "br",
    "span",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}
# ``rel`` is intentionally omitted here: it is managed by the ``link_rel``
# argument to ``nh3.clean`` (newer nh3 rejects specifying both).
_ALLOWED_ATTRS = {"a": {"href", "title"}}


def sanitize_html(html: str) -> str:
    """Sanitise HTML to a safe subset (drops scripts, event handlers, etc.)."""

    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        link_rel="noopener noreferrer nofollow",
    )


def strip_html(text: str) -> str:
    """Remove all HTML tags, returning plain text."""

    return nh3.clean(text, tags=set(), attributes={})


def clean_user_text(text: str, *, max_chars: int | None = None) -> str:
    """Normalise + defang free-text input.

    Removes control characters (except newline/tab), normalises Unicode, trims
    surrounding whitespace, and optionally truncates. Used at the API boundary
    before user text reaches the model or the database.
    """

    normalised = unicodedata.normalize("NFKC", text)
    cleaned = "".join(
        ch
        for ch in normalised
        if ch in ("\n", "\t") or not unicodedata.category(ch).startswith("C")
    )
    cleaned = cleaned.strip()
    if max_chars is not None and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip()
    return cleaned
