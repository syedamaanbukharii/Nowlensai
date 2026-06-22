"""Hybrid RAG: vector + lexical retrieval, fusion, reranking, compression."""

from nowlens.rag.citations import build_citations, format_context
from nowlens.rag.compression import compress_chunks
from nowlens.rag.fusion import reciprocal_rank_fusion
from nowlens.rag.lexical import BM25Retriever, PostgresFTSRetriever
from nowlens.rag.reranker import build_reranker
from nowlens.rag.retriever import HybridRetriever, adaptive_top_k
from nowlens.rag.types import Citation, RetrievalResult, RetrievedChunk
from nowlens.rag.vector_store import QdrantVectorStore

__all__ = [
    "BM25Retriever",
    "Citation",
    "HybridRetriever",
    "PostgresFTSRetriever",
    "QdrantVectorStore",
    "RetrievalResult",
    "RetrievedChunk",
    "adaptive_top_k",
    "build_citations",
    "build_reranker",
    "compress_chunks",
    "format_context",
    "reciprocal_rank_fusion",
]
