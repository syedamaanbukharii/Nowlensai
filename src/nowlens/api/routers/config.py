"""Read-only configuration view.

Exposes a redacted snapshot of effective settings for operators and for the
frontend config page. Secrets are never serialised — only non-sensitive
operational parameters and the catalogue of supported domains.
"""

from __future__ import annotations

from fastapi import APIRouter

from nowlens import __version__
from nowlens.api.deps import RequireOperator, SettingsDep
from nowlens.api.schemas import ConfigResponse
from nowlens.core.domains import all_domain_keys

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=ConfigResponse)
async def get_config(settings: SettingsDep, _: RequireOperator) -> ConfigResponse:
    llm = settings.llm
    chat_model = llm.ollama_chat_model if llm.provider == "ollama" else llm.groq_chat_model
    return ConfigResponse(
        environment=settings.environment,
        version=__version__,
        llm_provider=llm.provider,
        chat_model=chat_model,
        embedding_model=llm.ollama_embed_model,
        embedding_dim=llm.embedding_dim,
        vector_collection=settings.rag.collection,
        final_top_k=settings.rag.final_top_k,
        rerank_cross_encoder=settings.rag.use_cross_encoder,
        ai_cleaning=settings.ingestion.ai_cleaning,
        rate_limit_per_minute=settings.security.rate_limit_per_minute,
        langfuse_enabled=settings.observability.langfuse_enabled,
        supported_domains=list(all_domain_keys()),
    )
