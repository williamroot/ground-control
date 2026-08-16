"""Onboarding de cliente (Spec #1G-a, ADR D19) — orquestra Znuny + Postgres.

Fluxo de `onboard()` (numa única transação BYPASSRLS, D16):
  1. Resolve conflitos no Postgres (znuny_customer_id / subdomínio) ANTES de
     qualquer escrita no Znuny — conflito limpo ⇒ ZERO efeito colateral no GI.
  2. GI (via interface de T1.B): CustomerCompany + 1..N CustomerUser + senha,
     idempotente (a operação GertiAdmin faz check-before-add — D19).
  3. Postgres CROSS-TENANT com tenant_id EXPLÍCITO: gerti.tenant +
     gerti.tenant_branding + gerti.portal_user_role (1 por usuário).
Idempotente por `znuny_customer_id` / `subdomain` (reexecução não duplica;
re-onboarding após falha parcial reconcilia sem 409).

Tipos de domínio CONGELADOS na Fase 0 (T0.2). O router (T1.C) converte o corpo
Pydantic nestes dataclasses; T1.C preenche o corpo de `onboard`.
"""

from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar.integrations import znuny_customer_admin as gi
from gerti_sidecar.models.enums import PortalRole
from gerti_sidecar.models.portal_user_role import PortalUserRole
from gerti_sidecar.models.tenant import Tenant
from gerti_sidecar.models.tenant_branding import TenantBranding


class OnboardingConflict(ValueError):
    """Conflito limpo de onboarding (ex.: subdomínio já em uso por outro cliente)."""


@dataclasses.dataclass(slots=True)
class NewOnboardingUser:
    email: str
    first_name: str
    last_name: str
    password: str
    role: PortalRole = PortalRole.admin
    # Cadastro rico (T-R2.1): telefone/celular vão ao Znuny; ramal e a chave de
    # e-mail ficam em portal_user_role (ver justificativa na migration 0028).
    phone: str | None = None
    mobile: str | None = None
    extension: str | None = None
    email_intake_enabled: bool = True


@dataclasses.dataclass(slots=True)
class NewOnboarding:
    legal_name: str
    trade_name: str
    document: str
    subdomain: str
    znuny_customer_id: str
    znuny_instance_id: uuid.UUID
    display_name: str
    primary_color: str
    accent_color: str
    support_email: str | None
    logo_url: str | None
    users: list[NewOnboardingUser]
    created_by: str
    # Endereço e contato (T-R1.1) — opcionais, `gerti.tenant` é a dona (D-B).
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


@dataclasses.dataclass(slots=True)
class OnboardingResult:
    tenant_id: uuid.UUID
    subdomain: str
    created_users: list[str]


class TenantNotFound(LookupError):
    """Tenant inexistente (-> 404)."""


class ImmutableField(ValueError):
    """Tentativa de alterar campo imutável do cadastro (-> 422)."""


# Campos do cadastro que o console pode corrigir depois de criado (T-R1.2).
# `subdomain` e `znuny_customer_id` estão FORA de propósito: o primeiro é a
# chave do branding white-label e das sessões do portal; o segundo é o join com
# TODO ticket do cliente no Znuny. Mudar qualquer um dos dois não é "editar
# cadastro", é migrar cliente — e não vai acontecer por engano numa tela.
EDITABLE_TENANT_FIELDS = frozenset(
    {
        "legal_name",
        "trade_name",
        "document",
        "address_street",
        "address_number",
        "address_complement",
        "address_district",
        "address_city",
        "address_state",
        "address_zip",
        "contact_name",
        "contact_email",
        "contact_phone",
    }
)

IMMUTABLE_TENANT_FIELDS = frozenset({"subdomain", "znuny_customer_id", "id", "status"})


class OnboardingService:
    """Cross-tenant: recebe a factory BYPASSRLS (AdminSessionLocal, D16)."""

    def __init__(self, admin_factory: async_sessionmaker[AsyncSession]) -> None:
        self.admin_factory = admin_factory

    async def onboard(self, data: NewOnboarding) -> OnboardingResult:
        # Cross-tenant (BYPASSRLS, D16). A ORDEM importa: resolvemos TODOS os
        # conflitos no Postgres ANTES de qualquer escrita no Znuny, para que uma
        # rejeição limpa (OnboardingConflict) NÃO deixe CustomerCompany/User
        # órfãos no Znuny. As escritas GI são idempotentes (a operação GertiAdmin
        # faz check-before-add — ADR D19/T1.G), então um re-onboarding do mesmo
        # cliente reconcilia sem 409 mesmo após uma falha parcial anterior.
        async with self.admin_factory() as s:
            async with s.begin():
                tenant = (
                    await s.execute(
                        select(Tenant).where(Tenant.znuny_customer_id == data.znuny_customer_id)
                    )
                ).scalar_one_or_none()

                if tenant is None:
                    # Subdomínio precisa estar livre — se já aponta para OUTRO
                    # cliente, é um conflito limpo (4xx), não uma duplicata.
                    clash = (
                        await s.execute(select(Tenant).where(Tenant.subdomain == data.subdomain))
                    ).scalar_one_or_none()
                    if clash is not None:
                        raise OnboardingConflict(
                            f"subdomain {data.subdomain!r} já em uso por outro cliente"
                        )
                elif tenant.subdomain != data.subdomain:
                    # Re-onboarding do MESMO cliente, porém apontando para um
                    # subdomínio diferente do já registrado → conflito limpo.
                    raise OnboardingConflict(
                        f"znuny_customer_id {data.znuny_customer_id!r} já registrado "
                        f"com subdomínio {tenant.subdomain!r}"
                    )

                # Conflitos resolvidos (ZERO escrita no Znuny até aqui). Agora a
                # escrita GI idempotente: empresa + 1..N usuários + senhas. Uma
                # falha aqui (ZnunyUnavailable/ZnunyWriteError) faz rollback do
                # `s.begin()` → nenhum tenant parcial no Postgres.
                await gi.create_customer_company(data.znuny_customer_id, data.trade_name)
                for user in data.users:
                    await gi.create_customer_user(
                        login=user.email,
                        email=user.email,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        customer_id=data.znuny_customer_id,
                        phone=user.phone,
                        mobile=user.mobile,
                    )
                    await gi.set_password(user.email, user.password)

                if tenant is None:
                    tenant = Tenant(
                        legal_name=data.legal_name,
                        trade_name=data.trade_name,
                        document=data.document,
                        znuny_customer_id=data.znuny_customer_id,
                        znuny_instance_id=data.znuny_instance_id,
                        subdomain=data.subdomain,
                        address_street=data.address_street,
                        address_number=data.address_number,
                        address_complement=data.address_complement,
                        address_district=data.address_district,
                        address_city=data.address_city,
                        address_state=data.address_state,
                        address_zip=data.address_zip,
                        contact_name=data.contact_name,
                        contact_email=data.contact_email,
                        contact_phone=data.contact_phone,
                    )
                    s.add(tenant)
                    await s.flush()

                # Branding 1:1 — cria só se ainda não existir.
                branding = await s.get(TenantBranding, tenant.id)
                if branding is None:
                    s.add(
                        TenantBranding(
                            tenant_id=tenant.id,
                            display_name=data.display_name,
                            logo_url=data.logo_url,
                            primary_color=data.primary_color,
                            accent_color=data.accent_color,
                            support_email=data.support_email,
                        )
                    )
                    await s.flush()

                # 1 papel por usuário, idempotente por (tenant_id, lower(login)).
                for user in data.users:
                    login = user.email.lower()
                    existing = (
                        await s.execute(
                            select(PortalUserRole).where(
                                PortalUserRole.tenant_id == tenant.id,
                                func.lower(PortalUserRole.customer_login) == login,
                            )
                        )
                    ).scalar_one_or_none()
                    if existing is None:
                        s.add(
                            PortalUserRole(
                                tenant_id=tenant.id,
                                customer_login=login,
                                role=user.role,
                                extension=user.extension,
                                email_intake_enabled=user.email_intake_enabled,
                            )
                        )
                        await s.flush()

                tenant_id = tenant.id

        return OnboardingResult(
            tenant_id=tenant_id,
            subdomain=data.subdomain,
            created_users=[u.email.lower() for u in data.users],
        )

    async def update_registration(
        self,
        tenant_id: uuid.UUID,
        changes: dict[str, str | None],
    ) -> dict[str, tuple[str | None, str | None]]:
        """Corrige o cadastro de um cliente já criado (T-R1.2).

        `changes` traz APENAS os campos que o operador mandou (o router usa
        `exclude_unset`), então "não enviei" e "enviei vazio" são coisas
        diferentes: a primeira não mexe no campo, a segunda o limpa.

        Devolve o diff `{campo: (antes, depois)}` — é isso que vai para a
        auditoria. Sem o antes, a trilha diz que alguém mudou alguma coisa, não
        o que era.

        A escrita no Znuny acontece DENTRO da transação, igual ao `onboard()`:
        se o Znuny estiver fora, nada é gravado e o console recebe 503. O
        espelho pode divergir num crash entre as duas escritas — é idempotente,
        e um segundo PUT reconcilia.
        """
        unknown = set(changes) - EDITABLE_TENANT_FIELDS
        if unknown:
            raise ImmutableField(", ".join(sorted(unknown)))

        async with self.admin_factory() as s:
            async with s.begin():
                tenant = await s.get(Tenant, tenant_id)
                if tenant is None:
                    raise TenantNotFound(str(tenant_id))

                diff: dict[str, tuple[str | None, str | None]] = {}
                for field, new_value in changes.items():
                    old_value = getattr(tenant, field)
                    if old_value != new_value:
                        diff[field] = (old_value, new_value)

                if not diff:
                    return {}

                # Espelho no Znuny ANTES do commit (mesma ordem do onboard()).
                # Só chamamos o GI se algo que o Znuny guarda mudou — trocar só
                # o ramal do contato não precisa acordar o Znuny.
                mirrored = {
                    "trade_name",
                    "address_street",
                    "address_number",
                    "address_complement",
                    "address_zip",
                    "address_city",
                    "address_state",
                    "contact_name",
                    "contact_email",
                    "contact_phone",
                }
                if mirrored & set(diff):
                    merged = {f: changes.get(f, getattr(tenant, f)) for f in EDITABLE_TENANT_FIELDS}
                    await gi.update_customer_company(
                        tenant.znuny_customer_id,
                        company_name=merged["trade_name"] or tenant.trade_name,
                        street=_join_street(merged),
                        zip_code=merged["address_zip"],
                        city=_join_city(merged),
                        comment=_contact_comment(merged),
                    )

                for field, (_old, new_value) in diff.items():
                    setattr(tenant, field, new_value)

        return diff


def _join_street(f: dict[str, str | None]) -> str:
    """ "Rua X, 100 — Sala 2, Centro" a partir dos campos separados.

    O `customer_company` do Znuny tem UM campo `street`; nós guardamos quatro.
    Concatenar é o preço do espelho, e o dado fiel continua sendo o nosso.
    """
    head = ", ".join(p for p in (f.get("address_street"), f.get("address_number")) if p)
    tail = ", ".join(p for p in (f.get("address_complement"), f.get("address_district")) if p)
    return " — ".join(p for p in (head, tail) if p)


def _join_city(f: dict[str, str | None]) -> str:
    """ "Belo Horizonte/MG" — o Znuny tem `city`, não tem `state`."""
    return "/".join(p for p in (f.get("address_city"), f.get("address_state")) if p)


def _contact_comment(f: dict[str, str | None]) -> str:
    """Contato no campo livre `comments`: o customer_company não tem contato.

    Formato estável e legível para quem abre a empresa no painel do Znuny. Não é
    lido de volta por ninguém — a verdade é `gerti.tenant`.
    """
    parts = [
        p for p in (f.get("contact_name"), f.get("contact_email"), f.get("contact_phone")) if p
    ]
    return "Contato: " + " · ".join(parts) if parts else ""
