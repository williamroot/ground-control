"""Smoke test: consigo conectar no Postgres e ver schemas znuny+gerti."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_can_select_schemas(session: AsyncSession) -> None:
    result = await session.execute(
        text(
            "SELECT nspname FROM pg_namespace "
            "WHERE nspname IN ('znuny', 'gerti') "
            "ORDER BY nspname"
        )
    )
    schemas = [row[0] for row in result.all()]
    assert schemas == ["gerti", "znuny"]


@pytest.mark.asyncio
async def test_can_select_roles(session: AsyncSession) -> None:
    result = await session.execute(
        text(
            "SELECT rolname FROM pg_roles "
            "WHERE rolname IN ('gerti_app','gerti_admin','znuny_owner') "
            "ORDER BY rolname"
        )
    )
    roles = [row[0] for row in result.all()]
    assert roles == ["gerti_admin", "gerti_app", "znuny_owner"]
