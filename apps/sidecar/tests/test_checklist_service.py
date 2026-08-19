"""R13b — checklists personalizáveis.

*"Temos aqui configurações de feriados, checklists personalizáveis."* — 08:16

Este requisito ficou de fora da Onda 4 sem ninguém notar, e é a única lacuna
real dos 18 do vídeo (o R4 foi adiado pelo próprio cliente). Os aceites que
importam:

- **A13.4** — o agente aplica um modelo e marca item a item, com progresso.
- **A13.5** — aplicar o mesmo modelo duas vezes **não** duplica a lista.
- Isolamento — marcar item de outro cliente é **404**, não 403.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.checklist_service import (
    ChecklistError,
    ChecklistNotFound,
    ChecklistProgress,
    ChecklistTemplateService,
    NewTemplate,
    TicketChecklistService,
)
from gerti_sidecar.models import ChecklistTemplateItem, Tenant, TicketChecklistItem, ZnunyInstance

D = dt.date


async def _tenant(session, sub: str) -> Tenant:
    inst = (await session.execute(select(ZnunyInstance).limit(1))).scalar_one_or_none()
    if inst is None:
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
    t = Tenant(
        legal_name=sub,
        trade_name=sub,
        document=sub,
        znuny_customer_id=sub.upper(),
        znuny_instance_id=inst.id,
        subdomain=sub,
    )
    session.add(t)
    await session.flush()
    return t


# ── progresso (aritmética pura) ─────────────────────────────────────────────


def test_progress_never_divides_by_zero():
    """Modelo sem item não pode virar 100% nem estourar."""
    assert ChecklistProgress(total=0, done=0).percent == 0
    assert ChecklistProgress(total=5, done=2).percent == 40
    assert ChecklistProgress(total=3, done=3).percent == 100


# ── modelos ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_template_without_items_is_refused(session):
    """Modelo vazio só é descoberto depois de aplicado a um chamado."""
    svc = ChecklistTemplateService(session)
    with pytest.raises(ChecklistError, match="pelo menos um item"):
        await svc.create(NewTemplate(name="Vazio", items=[]), by="william")
    with pytest.raises(ChecklistError, match="pelo menos um item"):
        await svc.create(NewTemplate(name="Só espaços", items=["  ", ""]), by="william")


@pytest.mark.asyncio
async def test_a_template_needs_a_name(session):
    with pytest.raises(ChecklistError, match="nome"):
        await ChecklistTemplateService(session).create(
            NewTemplate(name="   ", items=["a"]), by="william"
        )


@pytest.mark.asyncio
async def test_two_templates_cannot_share_a_name(session):
    svc = ChecklistTemplateService(session)
    await svc.create(NewTemplate(name="Onboarding", items=["a"]), by="william")
    with pytest.raises(ChecklistError, match="já existe"):
        await svc.create(NewTemplate(name="Onboarding", items=["b"]), by="william")


@pytest.mark.asyncio
async def test_items_keep_the_order_they_were_written(session):
    """Checklist fora de ordem é checklist errado — é um procedimento."""
    svc = ChecklistTemplateService(session)
    t = await svc.create(
        NewTemplate(name="Troca de servidor", items=["Backup", "Desligar", "Trocar", "Testar"]),
        by="william",
    )
    items = await svc.items_of(t.id)
    assert [i.text for i in items] == ["Backup", "Desligar", "Trocar", "Testar"]
    assert [i.position for i in items] == [0, 1, 2, 3]


@pytest.mark.asyncio
async def test_deactivating_keeps_the_template(session):
    """Apagar sumiria com o histórico de quem já executou o procedimento."""
    svc = ChecklistTemplateService(session)
    t = await svc.create(NewTemplate(name="Antigo", items=["a"]), by="william")
    await svc.deactivate(t.id)
    assert [x.name for x in await svc.list_active()] == []
    assert [x.name for x in await svc.list_all()] == ["Antigo"]


# ── aplicação num chamado ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_applying_copies_the_items(engine, app_session_factory, session):
    t = await _tenant(session, "acme")
    tpl = await ChecklistTemplateService(session).create(
        NewTemplate(name="Onboarding", items=["Criar usuário", "Instalar antivírus"]),
        by="william",
    )
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = TicketChecklistService(s, t.id)
        cl = await svc.apply(znuny_ticket_id=4242, template_id=tpl.id, by="georgia")
        items = await svc.items_of(cl.id)
    assert cl.template_name == "Onboarding"
    assert [i.text for i in items] == ["Criar usuário", "Instalar antivírus"]
    assert all(not i.done for i in items)


@pytest.mark.asyncio
async def test_applying_twice_does_not_duplicate(engine, app_session_factory, session):
    """A13.5. A garantia é o UNIQUE no banco, não uma checagem em Python."""
    t = await _tenant(session, "acme")
    tpl = await ChecklistTemplateService(session).create(
        NewTemplate(name="Onboarding", items=["a", "b"]), by="william"
    )
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = TicketChecklistService(s, t.id)
        first = await svc.apply(znuny_ticket_id=1, template_id=tpl.id, by="georgia")
        second = await svc.apply(znuny_ticket_id=1, template_id=tpl.id, by="william")
        items = await svc.items_of(first.id)
    assert first.id == second.id
    assert len(items) == 2, "aplicar de novo duplicou os itens"


@pytest.mark.asyncio
async def test_editing_the_template_does_not_rewrite_what_was_executed(
    engine, app_session_factory, session
):
    """O registro do que o técnico marcou é o que ele VIU na hora.

    Mesmo princípio do `unit_price_at_event` na cobrança: o passado não se
    reescreve porque a configuração mudou.
    """
    t = await _tenant(session, "acme")
    tsvc = ChecklistTemplateService(session)
    tpl = await tsvc.create(NewTemplate(name="Procedimento", items=["Passo antigo"]), by="william")
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        cl = await TicketChecklistService(s, t.id).apply(
            znuny_ticket_id=7, template_id=tpl.id, by="georgia"
        )

    # O modelo é reescrito DEPOIS de aplicado.
    item = (
        (
            await session.execute(
                select(ChecklistTemplateItem).where(ChecklistTemplateItem.template_id == tpl.id)
            )
        )
        .scalars()
        .one()
    )
    item.text = "Passo novo, escrito depois"
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        items = await TicketChecklistService(s, t.id).items_of(cl.id)
    assert [i.text for i in items] == ["Passo antigo"]


@pytest.mark.asyncio
async def test_an_inactive_template_cannot_be_applied(engine, app_session_factory, session):
    t = await _tenant(session, "acme")
    tsvc = ChecklistTemplateService(session)
    tpl = await tsvc.create(NewTemplate(name="Aposentado", items=["a"]), by="william")
    await tsvc.deactivate(tpl.id)
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ChecklistNotFound):
            await TicketChecklistService(s, t.id).apply(
                znuny_ticket_id=9, template_id=tpl.id, by="georgia"
            )


# ── execução ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_marking_items_moves_the_progress(engine, app_session_factory, session):
    """A13.4 — o agente marca item a item e o progresso acompanha."""
    t = await _tenant(session, "acme")
    tpl = await ChecklistTemplateService(session).create(
        NewTemplate(name="Cinco passos", items=["a", "b", "c", "d", "e"]), by="william"
    )
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = TicketChecklistService(s, t.id)
        cl = await svc.apply(znuny_ticket_id=11, template_id=tpl.id, by="georgia")
        items = await svc.items_of(cl.id)
        assert (await svc.progress(cl.id)).percent == 0

        await svc.set_item(items[0].id, done=True, by="georgia")
        await svc.set_item(items[1].id, done=True, by="georgia")
        p = await svc.progress(cl.id)
    assert (p.done, p.total, p.percent) == (2, 5, 40)


@pytest.mark.asyncio
async def test_unmarking_clears_who_did_it(engine, app_session_factory, session):
    """'Feito por' num item não-feito seria informação errada na tela."""
    t = await _tenant(session, "acme")
    tpl = await ChecklistTemplateService(session).create(
        NewTemplate(name="Um passo", items=["a"]), by="william"
    )
    await session.commit()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = TicketChecklistService(s, t.id)
        cl = await svc.apply(znuny_ticket_id=12, template_id=tpl.id, by="georgia")
        item = (await svc.items_of(cl.id))[0]
        marked = await svc.set_item(item.id, done=True, by="georgia")
        assert marked.done_by == "georgia"
        assert marked.done_at is not None

        unmarked = await svc.set_item(item.id, done=False, by="william")
    assert unmarked.done is False
    assert unmarked.done_by is None
    assert unmarked.done_at is None


# ── isolamento entre clientes ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_marking_an_item_of_another_client_is_not_found(engine, app_session_factory, session):
    """404, nunca 403 — 403 confirmaria que o item existe.

    Rodado com o `tenant_id` do OUTRO cliente no serviço, que é exatamente o
    caminho do console (BYPASSRLS), onde a policy de RLS não vale. A Onda 3
    ensinou isso do jeito difícil.
    """
    acme = await _tenant(session, "acme")
    outra = await _tenant(session, "outra")
    tpl = await ChecklistTemplateService(session).create(
        NewTemplate(name="Compartilhado", items=["a"]), by="william"
    )
    await session.commit()

    async with tenant_session_scope(acme.id, factory=app_session_factory) as s:
        cl = await TicketChecklistService(s, acme.id).apply(
            znuny_ticket_id=99, template_id=tpl.id, by="georgia"
        )
        item = (await TicketChecklistService(s, acme.id).items_of(cl.id))[0]
        item_id = item.id

    # Mesma sessão do outro cliente tentando marcar o item da Acme.
    async with tenant_session_scope(outra.id, factory=app_session_factory) as s:
        with pytest.raises(ChecklistNotFound):
            await TicketChecklistService(s, outra.id).set_item(item_id, done=True, by="intruso")


@pytest.mark.asyncio
async def test_the_checklist_of_another_client_is_invisible(engine, app_session_factory, session):
    acme = await _tenant(session, "acme")
    outra = await _tenant(session, "outra")
    tpl = await ChecklistTemplateService(session).create(
        NewTemplate(name="Compartilhado", items=["a"]), by="william"
    )
    await session.commit()

    async with tenant_session_scope(acme.id, factory=app_session_factory) as s:
        await TicketChecklistService(s, acme.id).apply(
            znuny_ticket_id=1234, template_id=tpl.id, by="georgia"
        )

    # MESMO número de chamado, outro cliente: não pode enxergar nada.
    async with tenant_session_scope(outra.id, factory=app_session_factory) as s:
        found = await TicketChecklistService(s, outra.id).for_ticket(1234)
    assert found == []


@pytest.mark.asyncio
async def test_the_same_template_serves_two_clients_independently(
    engine, app_session_factory, session
):
    """O modelo é global; a execução, não."""
    acme = await _tenant(session, "acme")
    outra = await _tenant(session, "outra")
    tpl = await ChecklistTemplateService(session).create(
        NewTemplate(name="Padrão", items=["a", "b"]), by="william"
    )
    await session.commit()

    async with tenant_session_scope(acme.id, factory=app_session_factory) as s:
        svc = TicketChecklistService(s, acme.id)
        cl = await svc.apply(znuny_ticket_id=50, template_id=tpl.id, by="georgia")
        items = await svc.items_of(cl.id)
        await svc.set_item(items[0].id, done=True, by="georgia")

    async with tenant_session_scope(outra.id, factory=app_session_factory) as s:
        svc = TicketChecklistService(s, outra.id)
        cl2 = await svc.apply(znuny_ticket_id=50, template_id=tpl.id, by="william")
        p = await svc.progress(cl2.id)
    assert p.done == 0, "o progresso de um cliente vazou para o outro"

    async with tenant_session_scope(acme.id, factory=app_session_factory) as s:
        rows = (
            (await s.execute(select(TicketChecklistItem).where(TicketChecklistItem.done)))
            .scalars()
            .all()
        )
    assert len(rows) == 1
