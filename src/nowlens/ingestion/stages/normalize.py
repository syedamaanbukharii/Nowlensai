"""Normalize stage.

Unicode normalisation (NFKC), smart-quote/dash folding, zero-width character
removal, and bullet unification. Runs after cleaning and before chunking so
fingerprints (dedup) and embeddings see canonical text. Code fences are left
untouched apart from NFKC so commands remain byte-faithful.
"""

from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_QUOTES = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
    "\u2013": "-",
    "\u2014": "-",
    "\u00a0": " ",
}
_BULLETS = re.compile(r"^[\u2022\u25cf\u25aa\u25e6\u2043\u2219]\s*", re.MULTILINE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    for src, dst in _QUOTES.items():
        text = text.replace(src, dst)
    text = _BULLETS.sub("- ", text)
    # Trim trailing spaces on each line.
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()
