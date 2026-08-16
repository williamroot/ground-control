"""Associação cliente↔fila e fila padrão (T-R5.2, R5 do vídeo do Kleber).

*"Aqui a gente vai falar quais filas de atendimento o cara vai ter acesso.
Então a gente tem uma fila padrão. Tudo que entra por e-mail vem pra essa
fila."* (04:03)

Duas regras que valem a pena declarar antes do código:

1. **Um id de fila só é gravado se existir no Znuny AGORA.** A lista viva é a
   verdade; a gravação valida contra ela e recusa o conjunto inteiro (422) se
   qualquer id não existir. Gravar metade seria pior do que recusar.
2. **Exatamente uma padrão** quando há filas selecionadas. O banco garante o
   "no máximo uma" (índice parcial único `ux_tenant_queue_default`); o serviço
   garante o "pelo menos uma", que o banco não tem como exigir.

Escrita cross-tenant por `AdminSessionLocal` (BYPASSRLS) com `tenant_id`
explícito — padrão D16, o mesmo dos outros caminhos de console.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar.models.tenant import Tenant
from gerti_sidecar.models.tenant_queue import TenantQueue


class TenantNotFound(LookupError):
    """Tenant inexistente (-> 404)."""


class InvalidQueueSelection(ValueError):
    """Seleção recusada: fila inexistente, duplicada, ou padrão errada (-> 422)."""


@dataclasses.dataclass(frozen=True, slots=True)
class QueueSelection:
    znuny_queue_id: int
    is_default: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class TenantQueueRow:
    znuny_queue_id: int
    znuny_queue_name: str
    is_default: bool
    # Quem atende: grupo da fila no Znuny (A5.5). Read-only, derivado da lista
    # viva — não persistimos, porque é configuração do Znuny (invariante D21).
    group_id: int | None = None
    group_name: str | None = None


class TenantQueueService:
    def __init__(self, admin_factory: async_sessionmaker[AsyncSession], zao: Any) -> None:
        self._admin_factory = admin_factory
        self._zao = zao  # integrations.znuny_admin_objects (injetável nos testes)

    # ── leitura ──────────────────────────────────────────────────────────
    async def list_for_tenant(
        self, tenant_id: uuid.UUID, *, agent_login: str
    ) -> list[TenantQueueRow]:
        async with self._admin_factory() as s:
            if await s.get(Tenant, tenant_id) is None:
                raise TenantNotFound(str(tenant_id))
            rows = (
                (
                    await s.execute(
                        select(TenantQueue)
                        .where(TenantQueue.tenant_id == tenant_id)
                        .order_by(TenantQueue.znuny_queue_name)
                    )
                )
                .scalars()
                .all()
            )
        if not rows:
            return []

        # Enriquecer com grupo/atendentes é best-effort: se o Znuny estiver
        # fora, a tela ainda mostra as filas associadas (o nome está
        # denormalizado justamente para isto) em vez de quebrar inteira.
        by_id, group_names = await self._live_queues(agent_login=agent_login, quiet=True)
        out: list[TenantQueueRow] = []
        for r in rows:
            live = by_id.get(r.znuny_queue_id) or {}
            gid = _as_int(live.get("GroupID"))
            out.append(
                TenantQueueRow(
                    znuny_queue_id=r.znuny_queue_id,
                    # O nome vivo ganha do denormalizado quando ambos existem:
                    # renomear a fila no Znuny não pode deixar a tela mentindo.
                    znuny_queue_name=str(live.get("Name") or r.znuny_queue_name),
                    is_default=r.is_default,
                    group_id=gid,
                    group_name=group_names.get(gid) if gid is not None else None,
                )
            )
        return out

    # ── escrita ──────────────────────────────────────────────────────────
    async def replace_for_tenant(
        self,
        tenant_id: uuid.UUID,
        selections: list[QueueSelection],
        *,
        agent_login: str,
    ) -> list[TenantQueueRow]:
        """Substitui o conjunto inteiro. Idempotente: mesmo conjunto → mesmo estado."""
        ids = [q.znuny_queue_id for q in selections]
        if len(set(ids)) != len(ids):
            raise InvalidQueueSelection("fila repetida na seleção")

        # Lista vazia é legítima: é como se limpa a configuração e o cliente
        # volta ao comportamento antigo (fila `Raw`). Lista não-vazia exige
        # exatamente uma padrão — o banco garante o "no máximo uma", o "pelo
        # menos uma" só pode ser exigido aqui.
        defaults = [q for q in selections if q.is_default]
        if selections and len(defaults) != 1:
            raise InvalidQueueSelection("marque exatamente uma fila como padrão")

        by_id, group_names = await self._live_queues(agent_login=agent_login)
        missing = sorted(i for i in ids if i not in by_id)
        if missing:
            # Recusa o conjunto INTEIRO: nada gravado.
            raise InvalidQueueSelection(
                "fila inexistente no Znuny: " + ", ".join(str(i) for i in missing)
            )

        async with self._admin_factory() as s:
            async with s.begin():
                if await s.get(Tenant, tenant_id) is None:
                    raise TenantNotFound(str(tenant_id))

                # Índice parcial único: limpar TODOS os padrões e dar flush antes
                # de marcar o novo, senão mover o padrão de A para B colide.
                stale = delete(TenantQueue).where(TenantQueue.tenant_id == tenant_id)
                if ids:
                    stale = stale.where(TenantQueue.znuny_queue_id.notin_(ids))
                await s.execute(stale)
                existing = {
                    r.znuny_queue_id: r
                    for r in (
                        (
                            await s.execute(
                                select(TenantQueue).where(TenantQueue.tenant_id == tenant_id)
                            )
                        )
                        .scalars()
                        .all()
                    )
                }
                for row in existing.values():
                    row.is_default = False
                await s.flush()

                for sel in selections:
                    live = by_id[sel.znuny_queue_id]
                    name = str(live.get("Name") or sel.znuny_queue_id)
                    current = existing.get(sel.znuny_queue_id)
                    if current is None:
                        s.add(
                            TenantQueue(
                                tenant_id=tenant_id,
                                znuny_queue_id=sel.znuny_queue_id,
                                znuny_queue_name=name,
                                is_default=sel.is_default,
                            )
                        )
                    else:
                        current.znuny_queue_name = name
                        current.is_default = sel.is_default
                await s.flush()

        return await self.list_for_tenant(tenant_id, agent_login=agent_login)

    # ── fila padrão, para a abertura de chamado (T-R5.3) ─────────────────
    async def default_queue_name(self, tenant_id: uuid.UUID) -> str | None:
        """Nome da fila padrão do cliente, ou None se ele não configurou nenhuma."""
        async with self._admin_factory() as s:
            name = await s.scalar(
                select(TenantQueue.znuny_queue_name).where(
                    TenantQueue.tenant_id == tenant_id,
                    TenantQueue.is_default.is_(True),
                )
            )
        return str(name) if name is not None else None

    # ── apoio ────────────────────────────────────────────────────────────
    async def _live_queues(
        self, *, agent_login: str, quiet: bool = False
    ) -> tuple[dict[int, dict[str, Any]], dict[int, str]]:
        try:
            result = await self._zao.object_list("Queue", agent_login=agent_login)
        except Exception:  # na leitura degrada para vazio; na escrita, propaga
            if quiet:
                return {}, {}
            raise
        by_id: dict[int, dict[str, Any]] = {}
        for item in result.items:
            qid = _as_int(item.get("ID"))
            if qid is not None:
                by_id[qid] = item
        raw_groups = result.support.get("GroupList") or {}
        group_names: dict[int, str] = {}
        if isinstance(raw_groups, dict):
            for k, v in raw_groups.items():
                gid = _as_int(k)
                if gid is not None:
                    group_names[gid] = str(v)
        return by_id, group_names


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
