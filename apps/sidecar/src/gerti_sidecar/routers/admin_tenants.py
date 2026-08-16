"""/v1/admin/tenants* — listar, onboarding e detalhe de cliente (Spec #1G-a).

ADR D19. Todos exigem `get_admin_session` (401 sem sessão admin). Contratos
Pydantic CONGELADOS na Fase 0; T1.C preenche o corpo (orquestra GI +
gerti.tenant/branding/portal_user_role via AdminSessionLocal, D16).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain import audit_service
from gerti_sidecar.domain.onboarding_service import (
    ImmutableField,
    NewOnboarding,
    NewOnboardingUser,
    OnboardingConflict,
    OnboardingService,
    TenantNotFound,
)
from gerti_sidecar.integrations import znuny_customer_admin as gi
from gerti_sidecar.models.contract import Contract
from gerti_sidecar.models.enums import PortalRole
from gerti_sidecar.models.portal_user_role import PortalUserRole
from gerti_sidecar.models.tenant import Tenant
from gerti_sidecar.models.tenant_branding import TenantBranding
from gerti_sidecar.models.znuny_instance import ZnunyInstance

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


def _require_admin_factory() -> None:
    """Garante que a factory BYPASSRLS (AdminSessionLocal, D16) está disponível."""
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")


# ── entrada ──────────────────────────────────────────────────────────────
class OnboardingUserIn(BaseModel):
    email: str
    first_name: str
    last_name: str
    password: str
    role: Literal["admin", "helpdesk"] = "admin"
    # Cadastro rico (T-R2.1, 02:27 do vídeo). Telefone e celular vão para o
    # Znuny (dono da identidade); ramal e a chave de e-mail ficam do nosso lado
    # — ver justificativa na migration 0028.
    phone: str | None = Field(default=None, max_length=64)
    mobile: str | None = Field(default=None, max_length=64)
    extension: str | None = Field(default=None, max_length=32)
    active: bool = True
    email_intake_enabled: bool = True


class TenantRegistrationIn(BaseModel):
    """Corpo do PUT de cadastro (T-R1.2) — partial update.

    `exclude_unset` no router faz "não mandei" ≠ "mandei vazio": o primeiro não
    toca no campo, o segundo o limpa. `subdomain` e `znuny_customer_id` não
    aparecem aqui de propósito, e `extra="forbid"` transforma a tentativa de
    enviá-los em recusa explícita em vez de silêncio.
    """

    model_config = ConfigDict(extra="forbid")

    legal_name: str | None = Field(default=None, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    document: str | None = Field(default=None, max_length=32)
    address_street: str | None = Field(default=None, max_length=255)
    address_number: str | None = Field(default=None, max_length=32)
    address_complement: str | None = Field(default=None, max_length=255)
    address_district: str | None = Field(default=None, max_length=255)
    address_city: str | None = Field(default=None, max_length=255)
    address_state: str | None = Field(default=None, max_length=64)
    address_zip: str | None = Field(default=None, max_length=16)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)


class TenantUserIn(BaseModel):
    """Corpo do PUT de usuário do cliente (T-R2.1). Senha nunca passa por aqui."""

    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    mobile: str | None = Field(default=None, max_length=64)
    extension: str | None = Field(default=None, max_length=32)
    active: bool | None = None
    role: Literal["admin", "helpdesk"] | None = None
    email_intake_enabled: bool | None = None


class BrandingIn(BaseModel):
    display_name: str
    primary_color: str = "#2563EB"
    accent_color: str = "#1E40AF"
    support_email: str | None = None
    logo_url: str | None = None


class NewTenantBody(BaseModel):
    legal_name: str
    trade_name: str
    document: str
    subdomain: str
    znuny_customer_id: str
    # Endereço e contato já na criação (T-R1.1/T-R1.4): a etapa 1 do assistente
    # pede os dois, e sem isto o corpo chegaria e sumiria em silêncio. Todos
    # opcionais — quem não preencher segue criando como antes.
    address_street: str | None = Field(default=None, max_length=255)
    address_number: str | None = Field(default=None, max_length=32)
    address_complement: str | None = Field(default=None, max_length=255)
    address_district: str | None = Field(default=None, max_length=255)
    address_city: str | None = Field(default=None, max_length=255)
    address_state: str | None = Field(default=None, max_length=64)
    address_zip: str | None = Field(default=None, max_length=16)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)
    branding: BrandingIn
    users: list[OnboardingUserIn] = Field(min_length=1)


# ── saída ────────────────────────────────────────────────────────────────
class TenantSummary(BaseModel):
    id: str
    trade_name: str
    subdomain: str
    contract_count: int
    status: str


class TenantUserOut(BaseModel):
    customer_login: str
    role: str


class TenantUserRichOut(BaseModel):
    """Uma pessoa do cliente, juntando as duas metades da verdade (T-R2.2).

    Identidade e contato vêm do Znuny (dono, decisão D-C); papel, ramal e a
    chave de e-mail vêm de `gerti.portal_user_role`. `has_portal_access` é
    `false` para quem existe no Znuny e não tem papel — o caso que hoje é
    invisível no console.
    """

    customer_login: str
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    mobile: str = ""
    extension: str | None = None
    active: bool = True
    role: str | None = None
    email_intake_enabled: bool | None = None
    has_portal_access: bool = False


class TenantUsersOut(BaseModel):
    users: list[TenantUserRichOut]
    # `true` quando o Znuny está fora e a lista veio só da nossa tabela — a tela
    # precisa dizer isso, senão "faltou gente" parece exclusão.
    degraded: bool = False
    truncated: bool = False


class TenantContractOut(BaseModel):
    id: str
    code: str
    type: str
    status: str


class TenantDetail(BaseModel):
    id: str
    legal_name: str
    trade_name: str
    document: str
    subdomain: str
    znuny_customer_id: str
    status: str
    # Endereço e contato (T-R1.1). Nullable: cadastro criado antes da Onda 1
    # continua válido e aparece com os campos vazios, não quebrado.
    address_street: str | None = None
    address_number: str | None = None
    address_complement: str | None = None
    address_district: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_zip: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    branding: BrandingIn | None
    users: list[TenantUserOut]
    contracts: list[TenantContractOut]


class OnboardingResultOut(BaseModel):
    tenant: TenantDetail
    subdomain_to_register: str
    created_users: list[str]


# ── endpoints (stubs 501 — T1.C) ──────────────────────────────────────────
def _parse_tenant_id(tenant_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="tenant_not_found") from None


async def _build_detail(s: AsyncSession, tenant: Tenant) -> TenantDetail:
    branding = await s.get(TenantBranding, tenant.id)
    users = (
        (
            await s.execute(
                select(PortalUserRole)
                .where(PortalUserRole.tenant_id == tenant.id)
                .order_by(PortalUserRole.customer_login)
            )
        )
        .scalars()
        .all()
    )
    contracts = (
        (
            await s.execute(
                select(Contract).where(Contract.tenant_id == tenant.id).order_by(Contract.code)
            )
        )
        .scalars()
        .all()
    )
    return TenantDetail(
        id=str(tenant.id),
        legal_name=tenant.legal_name,
        trade_name=tenant.trade_name,
        document=tenant.document,
        subdomain=tenant.subdomain,
        znuny_customer_id=tenant.znuny_customer_id,
        status=tenant.status,
        address_street=tenant.address_street,
        address_number=tenant.address_number,
        address_complement=tenant.address_complement,
        address_district=tenant.address_district,
        address_city=tenant.address_city,
        address_state=tenant.address_state,
        address_zip=tenant.address_zip,
        contact_name=tenant.contact_name,
        contact_email=tenant.contact_email,
        contact_phone=tenant.contact_phone,
        branding=(
            BrandingIn(
                display_name=branding.display_name,
                primary_color=branding.primary_color,
                accent_color=branding.accent_color,
                support_email=branding.support_email,
                logo_url=branding.logo_url,
            )
            if branding is not None
            else None
        ),
        users=[TenantUserOut(customer_login=u.customer_login, role=u.role.value) for u in users],
        contracts=[
            TenantContractOut(id=str(c.id), code=c.code, type=c.type.value, status=c.status.value)
            for c in contracts
        ],
    )


@router.get("")
async def list_tenants(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[TenantSummary]:
    _require_admin_factory()
    assert db.AdminSessionLocal is not None
    async with db.AdminSessionLocal() as s:
        count_sq = (
            select(Contract.tenant_id, func.count().label("n"))
            .group_by(Contract.tenant_id)
            .subquery()
        )
        rows = (
            await s.execute(
                select(Tenant, func.coalesce(count_sq.c.n, 0))
                .outerjoin(count_sq, count_sq.c.tenant_id == Tenant.id)
                .order_by(Tenant.trade_name)
            )
        ).all()
    return [
        TenantSummary(
            id=str(t.id),
            trade_name=t.trade_name,
            subdomain=t.subdomain,
            contract_count=int(n),
            status=t.status,
        )
        for t, n in rows
    ]


@router.post("", status_code=201)
async def onboard_tenant(
    body: NewTenantBody,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> OnboardingResultOut:
    _require_admin_factory()
    assert db.AdminSessionLocal is not None

    # znuny_instance_id: §2.1 garante exatamente 1 Znuny. Resolvemos a única
    # linha; se houver mais de uma, escolhemos deterministicamente a mais antiga
    # (menor created_at) para manter o comportamento previsível.
    async with db.AdminSessionLocal() as s:
        instance = (
            await s.execute(select(ZnunyInstance).order_by(ZnunyInstance.created_at).limit(1))
        ).scalar_one_or_none()
    if instance is None:
        raise HTTPException(status_code=503, detail="no_znuny_instance")

    new = NewOnboarding(
        legal_name=body.legal_name,
        trade_name=body.trade_name,
        document=body.document,
        subdomain=body.subdomain,
        znuny_customer_id=body.znuny_customer_id,
        znuny_instance_id=instance.id,
        display_name=body.branding.display_name,
        primary_color=body.branding.primary_color,
        accent_color=body.branding.accent_color,
        support_email=body.branding.support_email,
        logo_url=body.branding.logo_url,
        address_street=body.address_street,
        address_number=body.address_number,
        address_complement=body.address_complement,
        address_district=body.address_district,
        address_city=body.address_city,
        address_state=body.address_state,
        address_zip=body.address_zip,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        users=[
            NewOnboardingUser(
                email=u.email,
                first_name=u.first_name,
                last_name=u.last_name,
                password=u.password,
                role=PortalRole(u.role),
                phone=u.phone,
                mobile=u.mobile,
                extension=u.extension,
                email_intake_enabled=u.email_intake_enabled,
            )
            for u in body.users
        ],
        created_by=admin["agent_login"],
    )

    service = OnboardingService(db.AdminSessionLocal)
    try:
        result = await service.onboard(new)
    except gi.ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except gi.ZnunyWriteError as exc:
        raise HTTPException(status_code=409, detail=f"znuny_write_error: {exc}") from exc
    except OnboardingConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, result.tenant_id)
        assert tenant is not None
        detail = await _build_detail(s, tenant)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=result.tenant_id,
        action="create",
        entity="tenant",
        entity_id=str(result.tenant_id),
        description=f"onboarding do tenant {body.trade_name} ({body.subdomain})",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"subdomain": body.subdomain, "znuny_customer_id": body.znuny_customer_id},
    )
    return OnboardingResultOut(
        tenant=detail,
        subdomain_to_register=result.subdomain,
        created_users=result.created_users,
    )


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantDetail:
    _require_admin_factory()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant_id(tenant_id)
    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        return await _build_detail(s, tenant)


@router.put("/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    body: TenantRegistrationIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantDetail:
    """Corrige o cadastro de um cliente já criado (T-R1.2, aceite A1.1/A1.2).

    Antes desta onda, errar o CNPJ na criação era definitivo: o router só sabia
    criar, listar e ler.
    """
    _require_admin_factory()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant_id(tenant_id)

    changes: dict[str, str | None] = dict(body.model_dump(exclude_unset=True))
    service = OnboardingService(db.AdminSessionLocal)
    try:
        diff = await service.update_registration(tid, changes)
    except TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="tenant_not_found") from exc
    except ImmutableField as exc:
        raise HTTPException(status_code=422, detail=f"campo imutável: {exc}") from exc
    except gi.ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except gi.ZnunyWriteError as exc:
        raise HTTPException(status_code=409, detail=f"znuny_write_error: {exc}") from exc

    if diff:
        await audit_service.record(
            actor_type="agent",
            actor_login=admin["agent_login"],
            tenant_id=tid,
            action="update",
            entity="tenant",
            entity_id=str(tid),
            description=f"cadastro alterado: {', '.join(sorted(diff))}",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            # Antes e depois, campo a campo: sem isso a trilha diz que alguém
            # mudou alguma coisa, não o que era.
            metadata={k: {"antes": v[0], "depois": v[1]} for k, v in diff.items()},
        )

    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, tid)
        if tenant is None:  # pragma: no cover - corrida improvável
            raise HTTPException(status_code=404, detail="tenant_not_found")
        return await _build_detail(s, tenant)


@router.get("/{tenant_id}/users")
async def list_tenant_users(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantUsersOut:
    """Pessoas do cliente, lendo o Znuny como fonte de verdade (T-R2.2, A2.5).

    A ficha do cliente listava `portal_user_role`, a NOSSA tabela — então quem
    fosse criado direto no painel do Znuny (ou, a partir do R9, auto-criado pelo
    PostMaster) simplesmente não existia para o console. Aqui as duas metades se
    juntam: identidade e contato do Znuny, papel e flags nossos.

    Znuny fora do ar não zera a tela: caímos para a nossa tabela e marcamos
    `degraded`, porque uma lista curta sem aviso é indistinguível de exclusão.
    """
    _require_admin_factory()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant_id(tenant_id)

    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        customer_id = tenant.znuny_customer_id
        roles = {
            r.customer_login.lower(): r
            for r in (
                (await s.execute(select(PortalUserRole).where(PortalUserRole.tenant_id == tid)))
                .scalars()
                .all()
            )
        }

    degraded = False
    truncated = False
    try:
        page = await gi.list_customer_users(customer_id)
        znuny_users = page.users
        truncated = page.truncated
    except gi.ZnunyUnavailable:
        znuny_users = []
        degraded = True

    out: list[TenantUserRichOut] = []
    seen: set[str] = set()
    for u in znuny_users:
        key = u.login.lower()
        seen.add(key)
        role = roles.get(key)
        out.append(
            TenantUserRichOut(
                customer_login=u.login,
                first_name=u.first_name,
                last_name=u.last_name,
                email=u.email,
                phone=u.phone,
                mobile=u.mobile,
                extension=role.extension if role else None,
                active=u.active,
                role=role.role.value if role else None,
                email_intake_enabled=role.email_intake_enabled if role else None,
                has_portal_access=role is not None,
            )
        )
    # Quem tem papel e o Znuny não devolveu: ou o Znuny está fora (degraded), ou
    # a pessoa foi removida de lá. Nos dois casos precisa aparecer, não sumir.
    for key, role in sorted(roles.items()):
        if key in seen:
            continue
        out.append(
            TenantUserRichOut(
                customer_login=role.customer_login,
                email=role.customer_login,
                extension=role.extension,
                role=role.role.value,
                email_intake_enabled=role.email_intake_enabled,
                has_portal_access=True,
            )
        )

    out.sort(key=lambda u: u.customer_login.lower())
    return TenantUsersOut(users=out, degraded=degraded, truncated=truncated)


@router.post("/{tenant_id}/users", status_code=201)
async def add_tenant_user(
    tenant_id: str,
    body: OnboardingUserIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantUserOut:
    _require_admin_factory()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant_id(tenant_id)
    login = body.email.lower()

    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        customer_id = tenant.znuny_customer_id

    # GI: cria o customer_user + senha no Znuny.
    try:
        await gi.create_customer_user(
            login=body.email,
            email=body.email,
            first_name=body.first_name,
            last_name=body.last_name,
            customer_id=customer_id,
            valid=body.active,
            phone=body.phone,
            mobile=body.mobile,
        )
        # `create_customer_user` é idempotente por login e RETORNA CEDO se a
        # pessoa já existir — sem aplicar telefone/celular/ValidID. Um update
        # logo em seguida garante que os campos ricos valham nos dois caminhos
        # (criar de fato, ou reconciliar um login que já estava lá).
        if body.phone is not None or body.mobile is not None or not body.active:
            await gi.update_customer_user(
                body.email,
                phone=body.phone,
                mobile=body.mobile,
                valid=body.active,
            )
        await gi.set_password(body.email, body.password)
    except gi.ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except gi.ZnunyWriteError as exc:
        raise HTTPException(status_code=409, detail=f"znuny_write_error: {exc}") from exc

    role = PortalRole(body.role)
    async with db.AdminSessionLocal() as s:
        async with s.begin():
            existing = (
                await s.execute(
                    select(PortalUserRole).where(
                        PortalUserRole.tenant_id == tid,
                        func.lower(PortalUserRole.customer_login) == login,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                s.add(
                    PortalUserRole(
                        tenant_id=tid,
                        customer_login=login,
                        role=role,
                        extension=body.extension,
                        email_intake_enabled=body.email_intake_enabled,
                    )
                )
            else:
                existing.role = role
                existing.extension = body.extension
                existing.email_intake_enabled = body.email_intake_enabled

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="create",
        entity="tenant_user",
        entity_id=login,
        description=f"usuário {login} cadastrado ({role.value})",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"role": role.value, "email_intake_enabled": body.email_intake_enabled},
    )
    return TenantUserOut(customer_login=login, role=role.value)


@router.put("/{tenant_id}/users/{login}")
async def update_tenant_user(
    tenant_id: str,
    login: str,
    body: TenantUserIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> TenantUserRichOut:
    """Edita ou **desativa** a pessoa do cliente (T-R2.1, aceite A2.4).

    Desativar é `ValidID = 2` no Znuny — nunca exclusão (invariante 3). A senha
    não passa por aqui: a op Perl rejeita qualquer chave com cara de senha.
    """
    _require_admin_factory()
    assert db.AdminSessionLocal is not None
    tid = _parse_tenant_id(tenant_id)
    key = login.strip().lower()
    if not key or "/" in key or "\\" in key:
        raise HTTPException(status_code=404, detail="user_not_found")

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="nada a alterar")

    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        customer_id = tenant.znuny_customer_id

    # A pessoa precisa pertencer a ESTE cliente. Sem esta checagem, um agente
    # editaria o usuário de qualquer empresa passando o tenant errado na URL.
    try:
        page = await gi.list_customer_users(customer_id)
    except gi.ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    target = next((u for u in page.users if u.login.lower() == key), None)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    znuny_fields = {"first_name", "last_name", "email", "phone", "mobile", "active"}
    if znuny_fields & set(changes):
        try:
            await gi.update_customer_user(
                target.login,
                first_name=changes.get("first_name"),
                last_name=changes.get("last_name"),
                email=changes.get("email"),
                phone=changes.get("phone"),
                mobile=changes.get("mobile"),
                valid=changes.get("active"),
            )
        except gi.ZnunyUnavailable as exc:
            raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
        except gi.ZnunyWriteError as exc:
            raise HTTPException(status_code=409, detail=f"znuny_write_error: {exc}") from exc

    async with db.AdminSessionLocal() as s:
        async with s.begin():
            role_row = (
                await s.execute(
                    select(PortalUserRole).where(
                        PortalUserRole.tenant_id == tid,
                        func.lower(PortalUserRole.customer_login) == key,
                    )
                )
            ).scalar_one_or_none()
            if role_row is None and (
                "role" in changes or "extension" in changes or "email_intake_enabled" in changes
            ):
                # Pessoa que existia só no Znuny ganhando acesso ao portal.
                role_row = PortalUserRole(
                    tenant_id=tid,
                    customer_login=target.login.lower(),
                    role=PortalRole(changes.get("role") or "helpdesk"),
                )
                s.add(role_row)
            if role_row is not None:
                if changes.get("role"):
                    role_row.role = PortalRole(changes["role"])
                if "extension" in changes:
                    role_row.extension = changes["extension"]
                if "email_intake_enabled" in changes:
                    role_row.email_intake_enabled = bool(changes["email_intake_enabled"])

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="update",
        entity="tenant_user",
        entity_id=target.login,
        description=f"usuário {target.login} alterado: {', '.join(sorted(changes))}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={k: v for k, v in changes.items() if k != "password"},
    )

    result = await list_tenant_users(tenant_id, admin)
    updated = next((u for u in result.users if u.customer_login.lower() == key), None)
    if updated is None:  # pragma: no cover - só se o Znuny sumir entre as chamadas
        raise HTTPException(status_code=503, detail="znuny_unavailable")
    return updated
