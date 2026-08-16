"""V-R5.3 / aceite A5.4 — a configuração de filas de um cliente é invisível ao outro.

Invariante 6 da campanha: isolamento entre clientes é **provado por teste**,
nunca presumido. `gerti.tenant_queue` nasceu nesta onda e carrega uma
informação de operação (quais filas o cliente acessa, e onde os chamados dele
caem), então precisa do mesmo tratamento das irmãs: FORCE RLS, e fail-closed
quando não há tenant na sessão.

O teste roda como `gerti_sidecar`, o papel SEM BYPASSRLS — é o papel que a
aplicação usa de verdade. Rodar como superusuário provaria nada.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.models import TenantQueue


async def _seed_queues(engine, a_id, b_id) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        s.add_all(
            [
                TenantQueue(
                    tenant_id=a_id,
                    znuny_queue_id=3,
                    znuny_queue_name="Suporte::N1",
                    is_default=True,
                ),
                TenantQueue(
                    tenant_id=b_id,
                    znuny_queue_id=9,
                    znuny_queue_name="Financeiro",
                    is_default=True,
                ),
            ]
        )
        await s.commit()


@pytest.mark.asyncio
async def test_tenant_queue_is_isolated_per_tenant(
    engine, app_session_factory, seed_two_tenants
) -> None:
    a_id, b_id = seed_two_tenants
    await _seed_queues(engine, a_id, b_id)

    async with tenant_session_scope(a_id, factory=app_session_factory) as s:
        rows = (await s.execute(select(TenantQueue))).scalars().all()
        assert [r.znuny_queue_id for r in rows] == [3]
        assert all(r.tenant_id == a_id for r in rows)

    async with tenant_session_scope(b_id, factory=app_session_factory) as s:
        rows = (await s.execute(select(TenantQueue))).scalars().all()
        assert [r.znuny_queue_id for r in rows] == [9]


@pytest.mark.asyncio
async def test_tenant_queue_without_guc_returns_nothing(
    engine, app_session_factory, seed_two_tenants
) -> None:
    """Sem `app.current_tenant` a consulta devolve zero linhas — fail-closed.

    Este é o caso que importa: um caminho de código que esqueceu de abrir o
    escopo de tenant precisa não ver NADA, e não ver TUDO.
    """
    a_id, b_id = seed_two_tenants
    await _seed_queues(engine, a_id, b_id)

    async with app_session_factory() as s:
        rows = (await s.execute(select(TenantQueue))).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_tenant_queue_write_into_another_tenant_is_blocked(
    engine, app_session_factory, seed_two_tenants
) -> None:
    """Escrever linha do tenant B com a sessão de A é recusado pelo WITH CHECK."""
    from sqlalchemy.exc import DBAPIError, IntegrityError

    a_id, b_id = seed_two_tenants

    with pytest.raises((DBAPIError, IntegrityError)):
        async with tenant_session_scope(a_id, factory=app_session_factory) as s:
            s.add(
                TenantQueue(
                    tenant_id=b_id,
                    znuny_queue_id=42,
                    znuny_queue_name="Fila do vizinho",
                    is_default=False,
                )
            )
            await s.flush()


@pytest.mark.asyncio
async def test_tenant_queue_has_force_rls_enabled(engine) -> None:
    """FORCE, não só ENABLE: sem FORCE, o dono da tabela ignora a policy."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        row = (
            await s.execute(
                text(
                    "select relrowsecurity, relforcerowsecurity from pg_class c "
                    "join pg_namespace n on n.oid = c.relnamespace "
                    "where n.nspname = 'gerti' and c.relname = 'tenant_queue'"
                )
            )
        ).one()
    assert row == (True, True)
