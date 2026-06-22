"""RAG component tests: fusion, compression, citations, reranking, lexical, and
the hybrid retriever orchestration."""

from __future__ import annotations

import pytest

from nowlens.rag.citations import build_citations, format_context
from nowlens.rag.compression import compress_chunk, compress_chunks
from nowlens.rag.fusion import reciprocal_rank_fusion
from nowlens.rag.lexical import BM25Retriever, tokenize
from nowlens.rag.reranker import LexicalOverlapReranker, build_reranker
from nowlens.rag.retriever import HybridRetriever, adaptive_top_k
from nowlens.rag.types import RetrievedChunk


def _chunk(chunk_id: str, text: str, *, document_id: str = "", **kw) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=chunk_id, text=text, score=0.0, document_id=document_id, **kw)


# --------------------------------------------------------------------------- #
# Fusion
# --------------------------------------------------------------------------- #


def test_rrf_rewards_agreement_across_lists() -> None:
    list_a = [_chunk("a", "x"), _chunk("b", "y"), _chunk("c", "z")]
    list_b = [_chunk("b", "y"), _chunk("a", "x"), _chunk("d", "w")]
    fused = reciprocal_rank_fusion([list_a, list_b], k=60)
    # 'a' and 'b' appear high in both lists, so they should top the ranking.
    assert {fused[0].chunk_id, fused[1].chunk_id} == {"a", "b"}
    assert fused[0].retriever == "rrf"


def test_rrf_respects_top_k_and_dedups_by_id() -> None:
    list_a = [_chunk("a", "x"), _chunk("b", "y")]
    list_b = [_chunk("a", "x"), _chunk("c", "z")]
    fused = reciprocal_rank_fusion([list_a, list_b], top_k=2)
    assert len(fused) == 2
    ids = [c.chunk_id for c in fused]
    assert len(ids) == len(set(ids))


def test_rrf_empty_input() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


# --------------------------------------------------------------------------- #
# Compression
# --------------------------------------------------------------------------- #


def test_compression_keeps_relevant_sentence() -> None:
    chunk = _chunk(
        "a",
        "Incident management routes tickets. The cafeteria menu changes weekly.",
    )
    compressed = compress_chunk(chunk, "how does incident management route tickets", ratio=0.6)
    assert "incident" in compressed.text.lower()
    assert "cafeteria" not in compressed.text.lower()


def test_compression_preserves_code_blocks() -> None:
    chunk = _chunk("a", "Intro prose here.\n```\nvar gr = new GlideRecord('incident');\n```")
    compressed = compress_chunk(chunk, "unrelated query about pizza", ratio=0.6)
    assert "GlideRecord" in compressed.text


def test_compression_never_empties_chunk() -> None:
    chunk = _chunk("a", "Alpha beta. Gamma delta. Epsilon zeta.")
    compressed = compress_chunk(chunk, "nothing matches here", ratio=0.6)
    assert compressed.text.strip()


def test_compress_chunks_preserves_count() -> None:
    chunks = [_chunk("a", "One two three. Four five six."), _chunk("b", "Seven eight.")]
    out = compress_chunks(chunks, "two", ratio=0.5)
    assert len(out) == 2


# --------------------------------------------------------------------------- #
# Citations
# --------------------------------------------------------------------------- #


def test_citations_collapse_by_document() -> None:
    chunks = [
        _chunk("c1", "first", document_id="d1", title="Doc One"),
        _chunk("c2", "second", document_id="d1", title="Doc One"),
        _chunk("c3", "third", document_id="d2", title="Doc Two"),
    ]
    citations, mapping = build_citations(chunks)
    assert len(citations) == 2
    assert mapping["c1"] == mapping["c2"] == 1
    assert mapping["c3"] == 2


def test_format_context_includes_indices() -> None:
    chunks = [_chunk("c1", "alpha", document_id="d1", title="Doc One")]
    _citations, mapping = build_citations(chunks)
    context = format_context(chunks, mapping)
    assert "[1]" in context
    assert "alpha" in context


def test_citation_snippet_truncated() -> None:
    long_text = "word " * 200
    citations, _ = build_citations([_chunk("c1", long_text, document_id="d1")])
    assert citations[0].snippet.endswith("…")


# --------------------------------------------------------------------------- #
# Lexical / BM25
# --------------------------------------------------------------------------- #


def test_tokenize_lowercases_and_splits() -> None:
    assert tokenize("GlideRecord, incident_table!") == ["gliderecord", "incident_table"]


async def test_bm25_ranks_by_term_match() -> None:
    chunks = [
        _chunk("a", "incident management routing rules"),
        _chunk("b", "change management approval workflow"),
        _chunk("c", "customer service case escalation"),
    ]
    retriever = BM25Retriever(chunks)
    hits = await retriever.search("incident routing", top_k=3)
    assert hits
    assert hits[0].chunk_id == "a"
    assert hits[0].retriever == "bm25"


async def test_bm25_empty_corpus_returns_empty() -> None:
    retriever = BM25Retriever([])
    assert await retriever.search("anything", top_k=5) == []


async def test_bm25_domain_filter() -> None:
    chunks = [
        _chunk("a", "incident management routing rules", domains=["itsm"]),
        _chunk("b", "customer service cases and accounts", domains=["csm"]),
        _chunk("c", "employee onboarding lifecycle tasks", domains=["hrsd"]),
    ]
    retriever = BM25Retriever(chunks)
    hits = await retriever.search("customer service", top_k=5, domains=["csm"])
    assert [h.chunk_id for h in hits] == ["b"]


# --------------------------------------------------------------------------- #
# Reranker
# --------------------------------------------------------------------------- #


async def test_lexical_reranker_orders_by_overlap() -> None:
    chunks = [
        _chunk("a", "completely unrelated content about gardening"),
        _chunk("b", "incident management routing and assignment"),
    ]
    reranked = await LexicalOverlapReranker().rerank("incident routing", chunks, top_k=2)
    assert reranked[0].chunk_id == "b"
    assert reranked[0].retriever == "rerank:lexical"


async def test_reranker_empty_query_passthrough() -> None:
    chunks = [_chunk("a", "x"), _chunk("b", "y")]
    reranked = await LexicalOverlapReranker().rerank("", chunks, top_k=1)
    assert len(reranked) == 1


def test_build_reranker_default_is_lexical() -> None:
    reranker = build_reranker(use_cross_encoder=False, cross_encoder_model="unused")
    assert isinstance(reranker, LexicalOverlapReranker)


# --------------------------------------------------------------------------- #
# adaptive_top_k
# --------------------------------------------------------------------------- #


def test_adaptive_top_k_bounds() -> None:
    assert adaptive_top_k("short", base=6, minimum=3, maximum=12) >= 3
    long_query = " ".join(["word"] * 100) + " and this vs that, plus more"
    assert adaptive_top_k(long_query, base=6, minimum=3, maximum=12) <= 12


def test_adaptive_top_k_grows_with_complexity() -> None:
    simple = adaptive_top_k("what is itsm", base=6)
    complex_q = adaptive_top_k(
        "compare itsm and csm, and explain overlap vs differences in detail", base=6
    )
    assert complex_q >= simple


# --------------------------------------------------------------------------- #
# HybridRetriever orchestration (with fakes)
# --------------------------------------------------------------------------- #


async def test_hybrid_retriever_returns_grounded_result(seeded_retriever: HybridRetriever) -> None:
    result = await seeded_retriever.retrieve("how does incident management work in itsm")
    assert result.chunks
    assert result.context
    assert result.citations
    assert "total_ms" in result.metrics
    # The top hit should be the ITSM incident chunk.
    assert result.chunks[0].chunk_id == "c1"


async def test_hybrid_retriever_domain_filter(seeded_retriever: HybridRetriever) -> None:
    result = await seeded_retriever.retrieve("cases", domains=["csm"])
    assert all("csm" in chunk.domains for chunk in result.chunks)


async def test_hybrid_retriever_no_hits_is_empty(embedder, vector_store, rag_settings) -> None:
    retriever = HybridRetriever(
        embedder=embedder,
        vector_store=vector_store,  # type: ignore[arg-type]
        lexical=BM25Retriever([]),
        reranker=LexicalOverlapReranker(),
        settings=rag_settings,
    )
    result = await retriever.retrieve("anything at all")
    assert result.chunks == []
    assert result.context == ""
    assert result.citations == []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
