"""`gerti.audit_log` não pode ser legível pelo papel de runtime — Spec #3 V5.

A tabela é operacional cross-tenant e **não tem RLS**: se `gerti_app` mantivesse
o SELECT herdado dos default privileges do schema, o papel usado pelo caminho de
cliente (`gerti_sidecar`, membro de `gerti_app`) conseguiria ler a trilha de
auditoria de todos os tenants. A barreira tem que ser o banco, não a disciplina
de quem escreve router.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_gerti_app_cannot_select_audit_log(
    engine: object, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """SELECT em audit_log pelo papel de runtime tem que ser negado pelo Postgres."""
    async with app_session_factory() as session:
        with pytest.raises(ProgrammingError) as exc:
            await session.execute(text("select count(*) from gerti.audit_log"))
    # InsufficientPrivilege (42501) — não é "0 linhas", é permissão negada.
    assert "permission denied" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_gerti_app_cannot_insert_audit_log(
    engine: object, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Escrita também é negada — a trilha só é alimentada pelo caminho admin."""
    async with app_session_factory() as session:
        with pytest.raises(ProgrammingError) as exc:
            await session.execute(
                text(
                    "insert into gerti.audit_log (actor_type, action, entity, description) "
                    "values ('agent','create','x','y')"
                )
            )
    assert "permission denied" in str(exc.value).lower()
