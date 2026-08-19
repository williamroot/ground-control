"""R16 — licenças, módulos por agente e o quadro da operação.

*"Hoje tem sete usuários ativos, a gente tem um total de nove. Total de
clientes cadastrados, 60. Contratos ativos, 43. […] Isso aqui impacta no
faturamento da plataforma para a gente."* (09:24)

O aceite que define a onda é o **caso da Georgia** (10:00): *"a Georgia só usa
tickets e não tem acesso remoto, então ela não vê o inventário"* — e o termo
de aceite é explícito quanto ao alcance: **nem pela URL direta**. Esconder o
item no menu não é controle de acesso.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from gerti_sidecar.domain.license_service import (
    LicenseError,
    LicenseService,
    NoSeatsAvailable,
    UnknownModule,
    validate_modules,
)
from gerti_sidecar.models import Contract, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractStatus, ContractType

D = dt.date


async def _seed_operation(session, *, tenants=2, active_contracts=3):
    inst = ZnunyInstance(
        name="i",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    made = 0
    for n in range(tenants):
        t = Tenant(
            legal_name=f"Cliente {n}",
            trade_name=f"C{n}",
            document=str(n),
            znuny_customer_id=f"C{n}",
            znuny_instance_id=inst.id,
            subdomain=f"c{n}",
        )
        session.add(t)
        await session.flush()
        for k in range(2):
            status = ContractStatus.active if made < active_contracts else ContractStatus.expired
            session.add(
                Contract(
                    tenant_id=t.id,
                    code=f"C{n}-{k}",
                    type=ContractType.hour_bank,
                    status=status,
                    starts_on=D(2026, 1, 1),
                    ends_on=D(2026, 12, 31),
                    initial_hours=10,
                    created_by="seed",
                )
            )
            if status == ContractStatus.active:
                made += 1
    await session.commit()


# ── catálogo fechado de módulos (A16.4) ─────────────────────────────────────


def test_an_invented_module_is_refused():
    with pytest.raises(UnknownModule, match="acesso_remoto"):
        validate_modules(["tickets", "acesso_remoto"])


def test_only_what_the_product_has_today_is_offered():
    """WhatsApp e acesso remoto ficam de fora até o recurso existir.

    Vender botão que não faz nada é pior do que não ter o botão.
    """
    from gerti_sidecar.models.licensing import MODULES

    assert MODULES == ("tickets", "inventory")


def test_modules_are_normalised_and_deduplicated():
    assert validate_modules(["inventory", "tickets", "tickets"]) == ["tickets", "inventory"]


# ── o quadrinho (A16.1) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_overview_counts_match_the_database(session):
    """Os números batem com a contagem direta — nunca um contador guardado."""
    await _seed_operation(session, tenants=3, active_contracts=4)
    svc = LicenseService(session)
    await svc.set_seats_total(9, by="william")
    for login in ("georgia", "william", "mariana"):
        await svc.assign(login, ["tickets"], by="william")
    await session.commit()

    data = await svc.overview()
    assert data.seats_total == 9
    assert data.seats_used == 3
    assert data.seats_free == 6
    assert data.tenants_total == 3
    assert data.contracts_active == 4

    direct = await session.scalar(
        text("select count(*) from gerti.contract where status = 'active'")
    )
    assert data.contracts_active == direct


@pytest.mark.asyncio
async def test_a_revoked_licence_frees_the_seat(session):
    await _seed_operation(session)
    svc = LicenseService(session)
    await svc.set_seats_total(2, by="william")
    await svc.assign("georgia", ["tickets"], by="william")
    await svc.assign("mariana", ["tickets"], by="william")
    assert (await svc.overview()).seats_free == 0

    await svc.revoke("georgia")
    assert (await svc.overview()).seats_free == 1
    # A linha FICA, para o histórico de quem teve licença.
    revoked = await svc.get("georgia")
    assert revoked is not None
    assert revoked.active is False
    assert revoked.revoked_at is not None


# ── recusa, não aviso (A16.2) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assigning_without_a_free_seat_is_refused_with_the_count(session):
    await _seed_operation(session)
    svc = LicenseService(session)
    await svc.set_seats_total(1, by="william")
    await svc.assign("william", ["tickets"], by="william")

    with pytest.raises(NoSeatsAvailable) as exc:
        await svc.assign("georgia", ["tickets"], by="william")
    # A contagem tem de estar na mensagem: sem ela o operador não sabe se
    # falta uma licença ou dez.
    assert "1 de 1" in str(exc.value)
    assert await svc.get("georgia") is None


@pytest.mark.asyncio
async def test_reactivating_a_revoked_agent_consumes_a_seat(session):
    """Senão o teto seria burlável revogando e reativando."""
    await _seed_operation(session)
    svc = LicenseService(session)
    await svc.set_seats_total(1, by="william")
    await svc.assign("georgia", ["tickets"], by="william")
    await svc.revoke("georgia")
    await svc.assign("william", ["tickets"], by="william")

    with pytest.raises(NoSeatsAvailable):
        await svc.assign("georgia", ["tickets"], by="william")


@pytest.mark.asyncio
async def test_changing_the_modules_of_a_licensed_agent_does_not_consume_a_seat(session):
    """Editar módulo não é atribuição nova — senão ninguém no teto editaria nada."""
    await _seed_operation(session)
    svc = LicenseService(session)
    await svc.set_seats_total(1, by="william")
    await svc.assign("georgia", ["tickets"], by="william")
    updated = await svc.assign("georgia", ["tickets", "inventory"], by="william")
    assert updated.modules == ["tickets", "inventory"]
    assert (await svc.overview()).seats_used == 1


@pytest.mark.asyncio
async def test_reducing_the_total_below_what_is_in_use_is_refused(session):
    """A alternativa seria revogar sozinho — tirar acesso sem ninguém decidir."""
    await _seed_operation(session)
    svc = LicenseService(session)
    await svc.set_seats_total(3, by="william")
    for login in ("a", "b", "c"):
        await svc.assign(login, ["tickets"], by="william")
    with pytest.raises(LicenseError, match="revogue antes"):
        await svc.set_seats_total(2, by="william")


# ── módulos por agente ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_georgia_has_tickets_and_not_inventory(session):
    """O caso do vídeo, no domínio. A prova de rota está em test_licensing_gate."""
    await _seed_operation(session)
    svc = LicenseService(session)
    await svc.set_seats_total(5, by="william")
    await svc.assign("georgia", ["tickets"], by="william")
    await svc.assign("william", ["tickets", "inventory"], by="william")

    assert await svc.modules_of("georgia") == ["tickets"]
    assert await svc.modules_of("william") == ["tickets", "inventory"]


@pytest.mark.asyncio
async def test_an_agent_without_a_licence_has_no_modules(session):
    await _seed_operation(session)
    assert await LicenseService(session).modules_of("ninguem") == []


@pytest.mark.asyncio
async def test_a_revoked_agent_has_no_modules(session):
    await _seed_operation(session)
    svc = LicenseService(session)
    await svc.set_seats_total(1, by="william")
    await svc.assign("georgia", ["tickets", "inventory"], by="william")
    await svc.revoke("georgia")
    assert await svc.modules_of("georgia") == []


# ── A16.6: a conexão da aplicação não enxerga licenciamento ─────────────────


@pytest.mark.asyncio
async def test_the_application_role_cannot_read_the_licence_tables(app_session_factory):
    """Imposto pelo BANCO (`REVOKE ALL ... FROM gerti_app`), não pelo código.

    É o que sobra de proteção se um dia alguém expuser licenciamento numa rota
    de cliente por engano.
    """
    from sqlalchemy.exc import ProgrammingError

    for table in ("platform_license", "agent_license"):
        async with app_session_factory() as s:
            with pytest.raises(ProgrammingError, match="permission denied"):
                await s.execute(text(f"select * from gerti.{table}"))


@pytest.mark.asyncio
async def test_the_licence_tables_have_no_tenant_column(session):
    """Licença é da OPERAÇÃO. Uma coluna de tenant convidaria a vazá-la."""
    for table in ("platform_license", "agent_license"):
        cols = (
            (
                await session.execute(
                    text(
                        "select column_name from information_schema.columns "
                        "where table_schema='gerti' and table_name=:t"
                    ),
                    {"t": table},
                )
            )
            .scalars()
            .all()
        )
        assert "tenant_id" not in cols
