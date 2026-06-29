"""Ingestion stage tests: each transform is pure/deterministic and tested in
isolation (normalize, chunk, dedup, enrich, validate, clean, extract, embed)."""

from __future__ import annotations

import pytest

from conftest import EMBED_DIM, FakeChatProvider, FakeEmbeddingProvider
from nowlens.ingestion.models import (
    Chunk,
    CrawlResult,
    EmbeddedChunk,
    ExtractedDocument,
    IngestionReport,
    StageOutcome,
    content_hash,
)
from nowlens.ingestion.stages.chunk import chunk_document, chunk_text
from nowlens.ingestion.stages.clean import AICleaner, rule_clean
from nowlens.ingestion.stages.dedup import deduplicate, hamming_distance, simhash
from nowlens.ingestion.stages.embed import embed_chunks
from nowlens.ingestion.stages.enrich import enrich_chunk, enrich_chunks
from nowlens.ingestion.stages.extract import extract
from nowlens.ingestion.stages.normalize import normalize
from nowlens.ingestion.stages.validate import validate_embedded


def _chunk(text: str, *, index: int = 0, metadata: dict | None = None) -> Chunk:
    return Chunk(
        chunk_id=f"c{index}",
        document_id="d1",
        text=text,
        index=index,
        metadata=metadata or {},
    )


# --------------------------------------------------------------------------- #
# models
# --------------------------------------------------------------------------- #


def test_content_hash_stable_and_distinct() -> None:
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")


def test_crawl_result_ok_property() -> None:
    assert CrawlResult(url="u", status_code=200, html="<html></html>").ok
    assert not CrawlResult(url="u", status_code=500, html="x").ok
    assert not CrawlResult(url="u", status_code=200, html="").ok
    assert not CrawlResult(url="u", status_code=200, html="x", error="boom").ok


def test_report_record_appends_stage() -> None:
    report = IngestionReport(url="u", document_id="d", success=False)
    report.record(StageOutcome("crawl", ok=True))
    assert report.stages[0].name == "crawl"


# --------------------------------------------------------------------------- #
# normalize
# --------------------------------------------------------------------------- #


def test_normalize_folds_smart_quotes_and_dashes() -> None:
    out = normalize("\u201cquoted\u201d \u2013 dash \u2014 emdash \u2018x\u2019")
    assert '"quoted"' in out
    assert "\u2013" not in out and "\u2014" not in out


def test_normalize_strips_zero_width_and_trailing_space() -> None:
    out = normalize("hello\u200bworld   \nfoo  ")
    assert "\u200b" not in out
    assert "   " not in out


def test_normalize_unifies_bullets() -> None:
    out = normalize("\u2022 first\n\u25cf second")
    assert out.count("- ") >= 2


# --------------------------------------------------------------------------- #
# chunk
# --------------------------------------------------------------------------- #


def test_chunk_text_respects_size() -> None:
    text = ". ".join(f"sentence number {i} with some words" for i in range(40))
    pieces = chunk_text(text, chunk_size=120, overlap=0)
    assert len(pieces) > 1
    assert all(len(p) <= 400 for p in pieces)


def test_chunk_text_keeps_code_fence_whole() -> None:
    code = "```\n" + "\n".join(f"line{i} = {i};" for i in range(10)) + "\n```"
    text = f"Intro paragraph.\n\n{code}\n\nOutro paragraph."
    pieces = chunk_text(text, chunk_size=80, overlap=0)
    assert any("```" in p and "line0 = 0;" in p and "line9 = 9;" in p for p in pieces)


def test_chunk_document_filters_min_chars_and_indexes() -> None:
    doc = ExtractedDocument(
        url="https://x/y",
        title="T",
        text="A long enough paragraph about incident management practices. " * 6,
    )
    chunks = chunk_document(doc, "doc-1", chunk_size=120, overlap=20, min_chunk_chars=50)
    assert chunks
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(c.metadata["title"] == "T" for c in chunks)
    assert all(c.document_id == "doc-1" for c in chunks)


# --------------------------------------------------------------------------- #
# dedup
# --------------------------------------------------------------------------- #


def test_simhash_similar_texts_close() -> None:
    a = simhash("incident management routing rules for the service desk team")
    b = simhash("incident management routing rules for the service desk teams")
    c = simhash("completely different content about cooking pasta at home tonight")
    assert hamming_distance(a, b) < hamming_distance(a, c)


def test_deduplicate_removes_exact_duplicate() -> None:
    chunks = [_chunk("identical text here", index=0), _chunk("identical text here", index=1)]
    kept, removed = deduplicate(chunks, max_distance=3)
    assert len(kept) == 1
    assert removed == 1


def test_deduplicate_keeps_distinct() -> None:
    chunks = [
        _chunk("incident management for IT teams", index=0),
        _chunk("software asset management licensing", index=1),
    ]
    kept, removed = deduplicate(chunks, max_distance=3)
    assert len(kept) == 2
    assert removed == 0
    assert "simhash" in kept[0].metadata


# --------------------------------------------------------------------------- #
# enrich
# --------------------------------------------------------------------------- #


def test_enrich_detects_code_headings_keywords() -> None:
    text = "## Incident Routing\nUse assignment rules.\n```\nvar gr = new GlideRecord();\n```"
    chunk = enrich_chunk(_chunk(text, metadata={"title": "ITSM"}))
    assert chunk.metadata["has_code"] is True
    assert "Incident Routing" in chunk.metadata["headings"]
    assert isinstance(chunk.metadata["keywords"], list)
    assert chunk.metadata["char_count"] == len(text)
    assert "itsm" in chunk.metadata["domains"]


def test_enrich_chunks_batch() -> None:
    out = enrich_chunks([_chunk("incident management", index=0), _chunk("flow designer", index=1)])
    assert len(out) == 2
    assert all("token_estimate" in c.metadata for c in out)


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #


def test_validate_accepts_good_chunks() -> None:
    embedded = [EmbeddedChunk(chunk=_chunk("text"), embedding=[0.1] * EMBED_DIM)]
    valid, problems = validate_embedded(embedded, expected_dim=EMBED_DIM)
    assert len(valid) == 1
    assert problems == []


def test_validate_rejects_wrong_dim_and_nonfinite() -> None:
    bad_dim = EmbeddedChunk(chunk=_chunk("a", index=0), embedding=[0.1] * (EMBED_DIM - 1))
    nan = EmbeddedChunk(chunk=_chunk("b", index=1), embedding=[float("nan")] * EMBED_DIM)
    empty = EmbeddedChunk(chunk=_chunk("   ", index=2), embedding=[0.1] * EMBED_DIM)
    valid, problems = validate_embedded([bad_dim, nan, empty], expected_dim=EMBED_DIM)
    assert valid == []
    assert len(problems) == 3


# --------------------------------------------------------------------------- #
# clean
# --------------------------------------------------------------------------- #


def test_rule_clean_drops_nav_and_collapses() -> None:
    raw = "Skip to main content\nReal heading\nReal heading\n\n\n\nBody text\nCopyright 2025 ACME"
    cleaned = rule_clean(raw)
    assert "Skip to main content" not in cleaned
    assert "Copyright" not in cleaned
    assert cleaned.count("Real heading") == 1
    assert "\n\n\n" not in cleaned


def test_rule_clean_preserves_code_fence() -> None:
    raw = "Intro\n```\nSkip to main content\nvar x = 1;\n```\nOutro"
    cleaned = rule_clean(raw)
    # Nav-looking line inside a code fence must survive.
    assert "Skip to main content" in cleaned
    assert "var x = 1;" in cleaned


async def test_ai_cleaner_falls_back_on_short_output() -> None:
    provider = FakeChatProvider(text="tiny")
    cleaner = AICleaner(provider, max_chars=6000)
    original = "This is a reasonably long document about incident management. " * 5
    result = await cleaner.clean(original)
    # Output too short relative to input -> fall back to the original text.
    assert result == original


# --------------------------------------------------------------------------- #
# extract
# --------------------------------------------------------------------------- #


def test_extract_pulls_title_and_main_content() -> None:
    html = """
    <html lang="en"><head><title>Doc Title</title></head>
    <body>
      <nav>menu noise should be dropped from extraction entirely</nav>
      <main>
        <h1>Incident Management</h1>
        <p>This is the primary body content that should be extracted cleanly.</p>
        <pre><code>var gr = new GlideRecord('incident');</code></pre>
      </main>
    </body></html>
    """
    doc = extract(CrawlResult(url="https://x/y", status_code=200, html=html))
    assert doc.title == "Doc Title"
    assert "Incident Management" in doc.text
    assert "primary body content" in doc.text
    assert "```" in doc.text
    assert "menu noise" not in doc.text
    assert doc.language == "en"


# --------------------------------------------------------------------------- #
# embed
# --------------------------------------------------------------------------- #


async def test_embed_chunks_one_vector_each() -> None:
    embedder = FakeEmbeddingProvider()
    chunks = [_chunk("incident", index=i) for i in range(3)]
    embedded = await embed_chunks(chunks, embedder, batch_size=2)
    assert len(embedded) == 3
    assert all(len(e.embedding) == EMBED_DIM for e in embedded)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
