"""`gerti.worker_heartbeat` não pode ser legível pelo papel de runtime (Spec #3).

Mesmo raciocínio de `test_audit_log_not_readable_by_app.py`: a tabela é
operacional cross-tenant e **não tem RLS**. Se `gerti_app` mantivesse o
SELECT herdado dos default privileges do schema, o papel de runtime
(`gerti_sidecar`, membro de `gerti_app`) conseguiria ler a prova de vida do
worker fora do caminho admin. A barreira tem que ser o banco.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_gerti_app_cannot_select_worker_heartbeat(
    engine: object, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """SELECT em worker_heartbeat pelo papel de runtime tem que ser negado pelo Postgres."""
    async with app_session_factory() as session:
        with pytest.raises(ProgrammingError) as exc:
            await session.execute(text("select count(*) from gerti.worker_heartbeat"))
    # InsufficientPrivilege (42501) — não é "0 linhas", é permissão negada.
    assert "permission denied" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_gerti_app_cannot_insert_worker_heartbeat(
    engine: object, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Escrita também é negada — o heartbeat só é alimentado pelo caminho admin."""
    async with app_session_factory() as session:
        with pytest.raises(ProgrammingError) as exc:
            await session.execute(
                text(
                    "insert into gerti.worker_heartbeat (worker, last_tick_at, ticks) "
                    "values ('x', now(), 1)"
                )
            )
    assert "permission denied" in str(exc.value).lower()
