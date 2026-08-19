"""R13b — checklists personalizáveis.

*"Temos aqui configurações de feriados, checklists personalizáveis."* — 08:16

Três decisões que valem explicação:

**Os itens da instância são CÓPIA, não referência.** Quando o modelo "troca de
servidor" é aplicado a um chamado, o texto de cada item é copiado. Editar o
modelo depois **não** muda o que já foi executado — o registro do que o técnico
marcou tem de continuar sendo o que ele viu na hora. É o mesmo princípio do
`unit_price_at_event` na cobrança: o passado não se reescreve porque a
configuração mudou.

**Aplicar duas vezes não duplica** (aceite A13.5). A garantia é o
`UNIQUE(znuny_ticket_id, template_id)` no banco, não uma checagem em Python —
duas requisições simultâneas passariam pela checagem e as duas gravariam.

**`tenant_id` explícito em toda consulta.** As tabelas têm RLS, mas o console
lê com o papel BYPASSRLS, onde as policies **não valem** — foi a lição da Onda
3, em que o consumo de um cliente aparecia no relatório de outro. Aqui o filtro
está no WHERE, e um teste prova o 404 entre clientes.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import (
    ChecklistTemplate,
    ChecklistTemplateItem,
    TicketChecklist,
    TicketChecklistItem,
)


class ChecklistError(Exception):
    """Recusa de regra (-> 422)."""


class ChecklistNotFound(Exception):
    """Não existe, ou não é deste cliente (-> 404)."""


@dataclasses.dataclass(frozen=True)
class NewTemplate:
    name: str
    items: list[str]
    description: str | None = None


@dataclasses.dataclass(frozen=True)
class ChecklistProgress:
    total: int
    done: int

    @property
    def percent(self) -> int:
        """0 quando não há item — nunca divide por zero nem inventa 100%."""
        return round(self.done * 100 / self.total) if self.total else 0


class ChecklistTemplateService:
    """CRUD dos modelos. Global: procedimento da Gerti, não de um cliente."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: NewTemplate, *, by: str) -> ChecklistTemplate:
        name = data.name.strip()
        if not name:
            raise ChecklistError("dê um nome ao modelo")
        items = [t.strip() for t in data.items if t.strip()]
        if not items:
            # Um modelo sem item é um modelo que não faz nada — e o agente só
            # descobre isso depois de aplicá-lo a um chamado.
            raise ChecklistError("um modelo precisa de pelo menos um item")

        template = ChecklistTemplate(
            name=name, description=(data.description or "").strip() or None, created_by=by
        )
        self.session.add(template)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise ChecklistError(f"já existe um modelo chamado {name!r}") from exc
        for position, text in enumerate(items):
            self.session.add(
                ChecklistTemplateItem(template_id=template.id, position=position, text=text)
            )
        await self.session.flush()
        return template

    async def list_active(self) -> list[ChecklistTemplate]:
        return list(
            (
                await self.session.execute(
                    select(ChecklistTemplate)
                    .where(ChecklistTemplate.active)
                    .order_by(ChecklistTemplate.name.asc())
                )
            )
            .scalars()
            .all()
        )

    async def list_all(self) -> list[ChecklistTemplate]:
        return list(
            (
                await self.session.execute(
                    select(ChecklistTemplate).order_by(
                        ChecklistTemplate.active.desc(), ChecklistTemplate.name.asc()
                    )
                )
            )
            .scalars()
            .all()
        )

    async def items_of(self, template_id: uuid.UUID) -> list[ChecklistTemplateItem]:
        return list(
            (
                await self.session.execute(
                    select(ChecklistTemplateItem)
                    .where(ChecklistTemplateItem.template_id == template_id)
                    .order_by(ChecklistTemplateItem.position.asc())
                )
            )
            .scalars()
            .all()
        )

    async def deactivate(self, template_id: uuid.UUID) -> ChecklistTemplate:
        """Desativa — nunca apaga.

        Apagar sumiria com o histórico de quem já executou o procedimento. É a
        mesma postura do `ValidID = 2` do Znuny.
        """
        template = await self.session.get(ChecklistTemplate, template_id)
        if template is None:
            raise ChecklistNotFound("modelo inexistente")
        template.active = False
        await self.session.flush()
        return template


class TicketChecklistService:
    """Aplicação e execução num chamado. SEMPRE escopado por `tenant_id`."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def apply(
        self, *, znuny_ticket_id: int, template_id: uuid.UUID, by: str
    ) -> TicketChecklist:
        """Aplica um modelo ao chamado. Idempotente por (chamado, modelo)."""
        existing = (
            await self.session.execute(
                select(TicketChecklist).where(
                    TicketChecklist.tenant_id == self.tenant_id,
                    TicketChecklist.znuny_ticket_id == znuny_ticket_id,
                    TicketChecklist.template_id == template_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing  # A13.5 — aplicar de novo não duplica

        template = await self.session.get(ChecklistTemplate, template_id)
        if template is None or not template.active:
            raise ChecklistNotFound("modelo inexistente ou inativo")
        items = await ChecklistTemplateService(self.session).items_of(template_id)
        if not items:  # pragma: no cover - `create` já impede
            raise ChecklistError("o modelo não tem itens")

        # Savepoint: a colisão do UNIQUE numa corrida é desfeita sem derrubar a
        # transação externa (que carrega o GUC do tenant).
        sp = await self.session.begin_nested()
        checklist = TicketChecklist(
            tenant_id=self.tenant_id,
            znuny_ticket_id=znuny_ticket_id,
            template_id=template_id,
            template_name=template.name,
            applied_by=by,
        )
        try:
            self.session.add(checklist)
            await self.session.flush()
        except IntegrityError:
            await sp.rollback()
            found = (
                await self.session.execute(
                    select(TicketChecklist).where(
                        TicketChecklist.tenant_id == self.tenant_id,
                        TicketChecklist.znuny_ticket_id == znuny_ticket_id,
                        TicketChecklist.template_id == template_id,
                    )
                )
            ).scalar_one_or_none()
            if found is None:  # pragma: no cover - corrida improvável
                raise
            return found

        for item in items:
            self.session.add(
                TicketChecklistItem(
                    checklist_id=checklist.id,
                    tenant_id=self.tenant_id,
                    position=item.position,
                    # CÓPIA do texto — editar o modelo depois não reescreve o
                    # que o técnico viu.
                    text=item.text,
                )
            )
        await self.session.flush()
        return checklist

    async def for_ticket(self, znuny_ticket_id: int) -> list[TicketChecklist]:
        return list(
            (
                await self.session.execute(
                    select(TicketChecklist)
                    .where(
                        TicketChecklist.tenant_id == self.tenant_id,
                        TicketChecklist.znuny_ticket_id == znuny_ticket_id,
                    )
                    .order_by(TicketChecklist.applied_at.asc())
                )
            )
            .scalars()
            .all()
        )

    async def items_of(self, checklist_id: uuid.UUID) -> list[TicketChecklistItem]:
        return list(
            (
                await self.session.execute(
                    select(TicketChecklistItem)
                    .where(
                        TicketChecklistItem.tenant_id == self.tenant_id,
                        TicketChecklistItem.checklist_id == checklist_id,
                    )
                    .order_by(TicketChecklistItem.position.asc())
                )
            )
            .scalars()
            .all()
        )

    async def progress(self, checklist_id: uuid.UUID) -> ChecklistProgress:
        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(TicketChecklistItem)
                .where(
                    TicketChecklistItem.tenant_id == self.tenant_id,
                    TicketChecklistItem.checklist_id == checklist_id,
                )
            )
            or 0
        )
        done = int(
            await self.session.scalar(
                select(func.count())
                .select_from(TicketChecklistItem)
                .where(
                    TicketChecklistItem.tenant_id == self.tenant_id,
                    TicketChecklistItem.checklist_id == checklist_id,
                    TicketChecklistItem.done,
                )
            )
            or 0
        )
        return ChecklistProgress(total=total, done=done)

    async def set_item(self, item_id: uuid.UUID, *, done: bool, by: str) -> TicketChecklistItem:
        """Marca ou desmarca um item.

        O `tenant_id` está no WHERE: item de outro cliente devolve **404**, e
        não 403 — 403 confirmaria que o item existe.
        """
        item = (
            await self.session.execute(
                select(TicketChecklistItem).where(
                    TicketChecklistItem.id == item_id,
                    TicketChecklistItem.tenant_id == self.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise ChecklistNotFound("item inexistente neste cliente")
        item.done = done
        # Desmarcar limpa a autoria: "feito por" de um item não-feito seria
        # informação errada na tela.
        item.done_at = dt.datetime.now(dt.UTC) if done else None
        item.done_by = by if done else None
        await self.session.flush()
        return item
