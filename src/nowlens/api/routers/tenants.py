"""Tenant administration endpoints (platform-admin only).

These are the *platform* control surface: creating tenants and provisioning a
tenant's initial users. They are restricted to admins of the default tenant (see
:func:`nowlens.api.deps.platform_admin`); a tenant's own admin operates only
within their tenant via the regular application endpoints, whose data access is
already tenant-scoped.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from nowlens.api.deps import PlatformAdmin, SessionDep
from nowlens.api.schemas import TenantCreate, TenantOut, TenantUserCreate, UserOut
from nowlens.core.exceptions import NotFoundError, ValidationError
from nowlens.db.models import Role, Tenant
from nowlens.db.repositories import AuditRepository, TenantRepository, UserRepository
from nowlens.security.audit import audit_event
from nowlens.security.password import hash_password

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _tenant_out(tenant: Tenant) -> TenantOut:
    return TenantOut(id=tenant.id, slug=tenant.slug, name=tenant.name, is_active=tenant.is_active)


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate, admin: PlatformAdmin, session: SessionDep
) -> TenantOut:
    tenants = TenantRepository(session)
    if await tenants.get_by_slug(payload.slug) is not None:
        raise ValidationError("A tenant with this slug already exists")
    tenant = await tenants.create(slug=payload.slug, name=payload.name)
    await audit_event(
        actor=admin.email,
        action="tenant.create",
        target=tenant.id,
        detail={"slug": tenant.slug},
        repository=AuditRepository(session, admin.tenant_id),
    )
    return _tenant_out(tenant)


@router.get("", response_model=list[TenantOut])
async def list_tenants(admin: PlatformAdmin, session: SessionDep) -> list[TenantOut]:
    return [_tenant_out(t) for t in await TenantRepository(session).list_all()]


@router.post("/{tenant_id}/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_tenant_user(
    tenant_id: str, payload: TenantUserCreate, admin: PlatformAdmin, session: SessionDep
) -> UserOut:
    """Provision a user inside ``tenant_id`` (used to seed a tenant's admin)."""

    if await TenantRepository(session).get(tenant_id) is None:
        raise NotFoundError("Tenant not found")
    users = UserRepository(session)
    # Email is globally unique, so it must be free across all tenants.
    if await users.get_by_email(payload.email) is not None:
        raise ValidationError("An account with this email already exists")
    user = await users.create(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=Role(payload.role),
        tenant_id=tenant_id,
    )
    await audit_event(
        actor=admin.email,
        action="tenant.create_user",
        target=user.id,
        detail={"tenant_id": tenant_id, "role": payload.role},
        repository=AuditRepository(session, admin.tenant_id),
    )
    return UserOut(id=user.id, email=user.email, role=str(user.role), is_active=user.is_active)
