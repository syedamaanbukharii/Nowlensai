"""Tenant administration schemas (platform-admin surface)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class TenantCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(default="", max_length=255)


class TenantOut(BaseModel):
    id: str
    slug: str
    name: str
    is_active: bool


class TenantUserCreate(BaseModel):
    """Provision a user inside a tenant (defaults to that tenant's admin)."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    role: Literal["viewer", "user", "operator", "admin"] = "admin"
