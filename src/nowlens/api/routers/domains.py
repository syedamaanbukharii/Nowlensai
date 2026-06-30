"""ServiceNow domain catalogue + feature-overlap analysis.

NowLens models ~two dozen ServiceNow capability areas (products, platform
sub-systems, and configuration constructs) with ``related`` edges between them.
These endpoints expose that catalogue to the UI and provide the structural
overlap analysis that backs the feature-overlap agent's "where do these two
products overlap?" reasoning.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from nowlens.api.deps import CurrentUser
from nowlens.core.domains import (
    Domain,
    all_domain_keys,
    analyze_overlap,
    get_domain,
)
from nowlens.core.exceptions import NotFoundError

router = APIRouter(prefix="/domains", tags=["domains"])


class DomainOut(BaseModel):
    key: str
    name: str
    category: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)


class OverlapRequest(BaseModel):
    domain_a: str
    domain_b: str


class OverlapResponse(BaseModel):
    domain_a: str
    domain_b: str
    related: bool
    shared_neighbours: list[str] = Field(default_factory=list)


def _domain_out(domain: Domain) -> DomainOut:
    return DomainOut(
        key=domain.key,
        name=domain.name,
        category=domain.category,
        description=domain.description,
        aliases=list(domain.aliases),
        related=list(domain.related),
    )


@router.get("", response_model=list[DomainOut])
async def list_domains(_: CurrentUser) -> list[DomainOut]:
    return [_domain_out(d) for key in all_domain_keys() if (d := get_domain(key)) is not None]


@router.get("/{key}", response_model=DomainOut)
async def get_domain_detail(key: str, _: CurrentUser) -> DomainOut:
    domain = get_domain(key)
    if domain is None:
        raise NotFoundError(f"Unknown domain '{key}'")
    return _domain_out(domain)


@router.post("/overlap", response_model=OverlapResponse)
async def overlap(payload: OverlapRequest, _: CurrentUser) -> OverlapResponse:
    try:
        result = analyze_overlap(payload.domain_a, payload.domain_b)
    except KeyError as exc:
        raise NotFoundError("Unknown domain in overlap analysis") from exc
    return OverlapResponse(
        domain_a=result.domain_a,
        domain_b=result.domain_b,
        related=result.related,
        shared_neighbours=result.shared_neighbours,
    )
