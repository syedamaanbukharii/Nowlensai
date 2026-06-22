"""Context compression.

Reduces each retrieved chunk to the sentences most relevant to the query before
they enter the prompt, which cuts token usage and noise without an extra model
call. The default scorer is dependency-free (query-term overlap); it keeps any
sentence scoring at least ``ratio`` of the best sentence's score, and always
keeps at least one sentence so we never drop a chunk entirely.

Technical examples (code blocks, tables) are preserved verbatim — compressing
them would corrupt the very content ServiceNow users need.
"""

from __future__ import annotations

import re

from nowlens.rag.lexical import tokenize
from nowlens.rag.types import RetrievedChunk

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_CODE_HINT_RE = re.compile(r"(```|\bvar\b|\bfunction\b|\bGlideRecord\b|\bcurrent\.|;\s*$)")


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _looks_like_code(sentence: str) -> bool:
    return bool(_CODE_HINT_RE.search(sentence))


def compress_chunk(chunk: RetrievedChunk, query: str, *, ratio: float = 0.6) -> RetrievedChunk:
    q_tokens = set(tokenize(query))
    sentences = _split_sentences(chunk.text)
    if len(sentences) <= 1 or not q_tokens:
        return chunk

    scored: list[tuple[float, int, str]] = []
    for position, sentence in enumerate(sentences):
        if _looks_like_code(sentence):
            score = float("inf")  # always keep technical content
        else:
            tokens = set(tokenize(sentence))
            score = (len(q_tokens & tokens) / len(q_tokens)) if tokens else 0.0
        scored.append((score, position, sentence))

    finite = [s for s in scored if s[0] != float("inf")]
    best = max((s[0] for s in finite), default=0.0)
    threshold = best * ratio

    kept = [
        (position, sentence)
        for score, position, sentence in scored
        if score == float("inf") or score >= threshold
    ]
    if not kept:
        # Never drop the whole chunk — keep the single best sentence.
        score, position, sentence = max(scored, key=lambda s: (s[0] != float("inf"), s[0]))
        kept = [(position, sentence)]

    kept.sort(key=lambda item: item[0])  # restore original order
    compressed_text = " ".join(sentence for _, sentence in kept)
    new_chunk = chunk.copy_with_score(chunk.score)
    new_chunk.text = compressed_text
    new_chunk.metadata = {**chunk.metadata, "compressed": len(compressed_text) < len(chunk.text)}
    return new_chunk


def compress_chunks(
    chunks: list[RetrievedChunk], query: str, *, ratio: float = 0.6
) -> list[RetrievedChunk]:
    return [compress_chunk(chunk, query, ratio=ratio) for chunk in chunks]
