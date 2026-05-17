"""Alembic env (async) — usa DATABASE_URL e o metadata do sidecar."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from gerti_sidecar.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# DATABASE_URL pode vir de env ou do alembic.ini (cmd `-x url=...`)
db_url = os.environ.get("DATABASE_URL") or context.get_x_argument(as_dictionary=True).get("url")
if not db_url:
    raise RuntimeError("DATABASE_URL não definido nem via env nem via -x url=...")
config.set_main_option("sqlalchemy.url", db_url)


def include_object(object, name, type_, reflected, compare_to) -> bool:
    """Alembic só gerencia o schema gerti; ignora o schema znuny."""
    if type_ == "table" and getattr(object, "schema", None) == "znuny":
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="gerti",
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="gerti",
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
