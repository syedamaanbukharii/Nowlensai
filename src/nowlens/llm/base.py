"""Provider-agnostic LLM abstraction.

The rest of the system depends only on the :class:`LLMProvider` and
:class:`EmbeddingProvider` protocols defined here — never on a concrete vendor.
Swapping Ollama for Groq (or adding a new backend) is a factory/config change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class ChatMessage:
    role: Role
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class ChatUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class ChatResult:
    content: str
    model: str
    provider: str
    usage: ChatUsage = field(default_factory=ChatUsage)
    finish_reason: str | None = None


@dataclass(slots=True)
class ChatChunk:
    """A streamed delta. ``done`` marks the terminal chunk."""

    delta: str
    done: bool = False
    usage: ChatUsage | None = None


class LLMProvider(ABC):
    """Chat completion provider."""

    name: str

    @abstractmethod
    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """Return a full completion."""

    @abstractmethod
    def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Yield incremental :class:`ChatChunk` deltas."""

    async def aclose(self) -> None:  # noqa: B027 - optional override, default no-op
        """Release any held resources (HTTP clients, etc.)."""


class EmbeddingProvider(ABC):
    """Text embedding provider."""

    name: str
    dimension: int

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]

    async def aclose(self) -> None:  # noqa: B027 - optional override, default no-op
        ...
