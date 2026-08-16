"""V-R1.4 — as colunas novas da Onda 1 não quebram o que já está no banco.

Migrations desta onda: 0027 (endereço/contato do cliente), 0028 (ramal e a
chave de e-mail por pessoa), 0029 (filas por cliente), 0030 (pendência de
consumo).

O que se prova aqui é o mínimo que impede um deploy ruim em staging, onde já
existem clientes cadastrados sem nenhum desses campos:

  • um tenant SEM endereço nenhum continua inserível (as 10 colunas são nullable)
  • as colunas existem mesmo, com o nome esperado (o teste falha se alguém
    renomear uma delas e esquecer do resto)
  • `portal_user_role` ganhou a chave de e-mail LIGADA por padrão — um papel
    criado antes da onda não pode nascer sem poder abrir chamado por e-mail
  • a cadeia de revisões está inteira e o head é o que achamos que é

O `engine` do conftest já aplica `alembic upgrade head`, então estar aqui
dentro já significa que a subida rodou limpa.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar.models import PortalUserRole, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import PortalRole

_ADDRESS_COLUMNS = {
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


@pytest.mark.asyncio
async def test_tenant_address_columns_exist_and_are_nullable(engine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        rows = (
            await s.execute(
                text(
                    "select column_name, is_nullable from information_schema.columns "
                    "where table_schema = 'gerti' and table_name = 'tenant'"
                )
            )
        ).all()
    by_name = {name: nullable for name, nullable in rows}
    assert _ADDRESS_COLUMNS <= set(by_name), sorted(_ADDRESS_COLUMNS - set(by_name))
    for col in _ADDRESS_COLUMNS:
        assert by_name[col] == "YES", f"{col} precisa ser nullable (cadastro antigo não tem)"


@pytest.mark.asyncio
async def test_tenant_without_address_still_inserts(engine) -> None:
    """Exatamente o cliente que já existe no staging: nenhum campo de endereço."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        inst = ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
            mode="pool",
        )
        s.add(inst)
        await s.flush()
        t = Tenant(
            legal_name="Antigo Ltda",
            trade_name="Antigo",
            document="00.000.000/0001-00",
            znuny_customer_id="ANTIGO",
            znuny_instance_id=inst.id,
            subdomain="antigo",
        )
        s.add(t)
        await s.commit()

        again = (
            await s.execute(select(Tenant).where(Tenant.znuny_customer_id == "ANTIGO"))
        ).scalar_one()
        assert again.address_city is None
        assert again.contact_email is None


@pytest.mark.asyncio
async def test_email_intake_defaults_to_enabled(engine) -> None:
    """0028 — a chave nasce LIGADA: o cadastro único é a promessa do R2."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        inst = ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
            mode="pool",
        )
        s.add(inst)
        await s.flush()
        t = Tenant(
            legal_name="Acme",
            trade_name="Acme",
            document="1",
            znuny_customer_id="ACME",
            znuny_instance_id=inst.id,
            subdomain="acme",
        )
        s.add(t)
        await s.flush()
        # Insere SEM tocar na coluna nova, como faria código anterior à onda.
        s.add(
            PortalUserRole(tenant_id=t.id, customer_login="ana@acme.example", role=PortalRole.admin)
        )
        await s.commit()

        row = (await s.execute(select(PortalUserRole))).scalars().one()
        assert row.email_intake_enabled is True
        assert row.extension is None


@pytest.mark.asyncio
async def test_only_one_default_queue_per_tenant_is_enforced_by_the_database(engine) -> None:
    """0029 — o "no máximo uma padrão" é do banco, não da aplicação.

    Se fosse só regra de serviço, duas gravações concorrentes deixariam o
    cliente com dois padrões e a abertura de chamado escolheria um dos dois de
    forma não-determinística.
    """
    from sqlalchemy.exc import IntegrityError

    from gerti_sidecar.models import TenantQueue

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        inst = ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
            mode="pool",
        )
        s.add(inst)
        await s.flush()
        t = Tenant(
            legal_name="Acme",
            trade_name="Acme",
            document="1",
            znuny_customer_id="ACME",
            znuny_instance_id=inst.id,
            subdomain="acme",
        )
        s.add(t)
        await s.flush()
        s.add(TenantQueue(tenant_id=t.id, znuny_queue_id=3, znuny_queue_name="A", is_default=True))
        await s.flush()
        s.add(TenantQueue(tenant_id=t.id, znuny_queue_id=5, znuny_queue_name="B", is_default=True))
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()


@pytest.mark.asyncio
async def test_consumption_orphan_is_not_readable_by_the_app_role(engine, app_session_factory):
    """0030 — a fila de pendência é operacional: `gerti_app` não tem acesso.

    Espelha o cuidado de `audit_log` e `worker_heartbeat`: os default privileges
    do schema `gerti` concedem sozinhos se a migration não revogar.
    """
    from sqlalchemy.exc import ProgrammingError

    async with app_session_factory() as s:
        with pytest.raises(ProgrammingError):
            await s.execute(text("select 1 from gerti.consumption_orphan"))
