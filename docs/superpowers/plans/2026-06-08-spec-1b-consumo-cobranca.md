# Spec #1B — Cobrança/consumo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconciliar o tempo lançado pelos agentes no Znuny (`time_accounting`) em `gerti.consumption_event` no contrato vinculado — debitando o saldo já exibido no portal — e fechar ciclos vencidos automaticamente, tudo num worker dedicado que puxa via Generic Interface.

**Architecture:** Op GI nova `TimeAccountingSince` no webservice `GertiTicket` (leitura pura da tabela nativa). No sidecar, `reconciliation_service` puxa as entradas, resolve ticket→contrato (cross-tenant BYPASSRLS), e grava `consumption_event` por-tenant (RLS-subject) com idempotência determinística (`uuid5`); `cycle_closer` fecha ciclos vencidos via `CycleService.close()`. Um serviço compose `sidecar-worker` (mesma imagem, command próprio) roda o loop. `ConsumptionService`/`balance()`/`CycleService` reusados sem alteração.

**Tech Stack:** Znuny 7.2.3 (Perl/GI, `Kernel::System::DB`), FastAPI + SQLAlchemy 2 async + Alembic + asyncio + structlog (sidecar), pytest/testcontainers. Spec: `docs/superpowers/specs/2026-06-08-spec-1b-consumo-cobranca-design.md`.

**Convenções de gate (zero-tolerância):**
- Sidecar: `cd apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q` (testcontainers exige Docker; o `DATABASE_URL` dummy é exigido na coleta).
- Znuny: `perl -c` no build da imagem é o gate de sintaxe.
- Stack base intocada: `make test` (24 asserts) continua verde.
- Commits `feat(#1B ...)`/`test(#1B ...)`, terminando com `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## FASE 1 — Znuny: op GI `TimeAccountingSince`

### Task 1: Operação `TimeAccountingSince.pm` + entrada no YAML + bake no Dockerfile

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingSince.pm`
- Modify: `znuny/webservices/GertiTicket.yml`
- Modify: `znuny/Dockerfile` (bloco GertiTicket: +1 COPY e +1 no loop `perl -c`)

- [ ] **Step 1: Escrever o módulo** (espelha `_CheckAccessToken` dos outros GertiTicket; leitura pura via `Kernel::System::DB`)

```perl
# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingSince.pm
# --
# Gerti — custom GI operation (Spec #1B). Read-only pull of native Znuny
# time_accounting rows (agent TimeUnits) with id > SinceId, for the sidecar
# reconciliation worker to turn into gerti.consumption_event. Read-only: never
# writes Znuny. Upgrade-safe Custom/ overlay (same as the other GertiTicket ops).
# --
package Kernel::GenericInterface::Operation::GertiTicket::TimeAccountingSince;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(Kernel::GenericInterface::Operation::Common);

our $ObjectManagerDisabled = 1;

sub new {
    my ( $Type, %Param ) = @_;
    my $Self = {};
    bless( $Self, $Type );
    for my $Needed (qw(DebuggerObject WebserviceID)) {
        return { Success => 0, ErrorMessage => "Got no $Needed!" } if !$Param{$Needed};
        $Self->{$Needed} = $Param{$Needed};
    }
    return $Self;
}

sub Run {
    my ( $Self, %Param ) = @_;

    return $Self->ReturnError(
        ErrorCode => 'TimeAccountingSince.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    my $SinceId = $D->{SinceId};
    $SinceId = 0 if !defined $SinceId || $SinceId !~ /^\d+$/;
    my $Limit = $D->{Limit};
    $Limit = 500 if !defined $Limit || $Limit !~ /^\d+$/ || $Limit < 1 || $Limit > 2000;

    my $DBObject = $Kernel::OM->Get('Kernel::System::DB');
    return $Self->ReturnError(
        ErrorCode => 'TimeAccountingSince.DBError', ErrorMessage => 'prepare failed',
    ) if !$DBObject->Prepare(
        SQL => 'SELECT id, ticket_id, article_id, time_unit, create_time '
            . 'FROM time_accounting WHERE id > ? ORDER BY id ASC',
        Bind  => [ \$SinceId ],
        Limit => $Limit,
    );

    my @Entries;
    my $MaxId = $SinceId;
    while ( my @Row = $DBObject->FetchrowArray() ) {
        push @Entries, {
            Id        => $Row[0],
            TicketId  => $Row[1],
            ArticleId => $Row[2],
            TimeUnit  => $Row[3],
            Created   => $Row[4],
        };
        $MaxId = $Row[0] if $Row[0] > $MaxId;
    }

    return {
        Success => 1,
        Data    => { Entries => \@Entries, MaxId => $MaxId },
    };
}

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;
    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAdmin::AccessToken') || '';
    return $Self->ReturnError( ErrorCode => 'GertiTicket.AuthFail', ErrorMessage => 'invalid AccessToken.' )
        if !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected;
    return;
}

1;
```

- [ ] **Step 2: Adicionar a operação ao `GertiTicket.yml`**

Em `znuny/webservices/GertiTicket.yml`, sob `Provider.Operation`, adicionar (após `FormMeta:`):
```yaml
    TimeAccountingSince:
      Description: Read native time_accounting rows since a cursor (Spec #1B)
      Type: GertiTicket::TimeAccountingSince
```
E sob `Provider.Transport.Config.RouteOperationMapping` (após o mapeamento de `FormMeta`):
```yaml
        TimeAccountingSince:
          RequestMethod:
          - POST
          Route: /TimeAccounting/Since
```

- [ ] **Step 3: Bake no Dockerfile** (bloco GertiTicket, ~linha 166-188)

No `znuny/Dockerfile`, adicionar uma linha COPY junto às outras 5 ops GertiTicket:
```dockerfile
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingSince.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingSince.pm
```
E incluir `TimeAccountingSince` no loop `perl -c` (a linha `for m in TicketCreate TicketSearch TicketGet TicketReply FormMeta ; do` vira):
```dockerfile
    for m in TicketCreate TicketSearch TicketGet TicketReply FormMeta TimeAccountingSince ; do \
```

- [ ] **Step 4: Build da imagem (gate `perl -c`)**

Run: `docker compose build znuny-web`
Expected: build conclui; aparece `.../GertiTicket/TimeAccountingSince.pm syntax OK` no log.

- [ ] **Step 5: Commit**

```bash
git add znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingSince.pm znuny/webservices/GertiTicket.yml znuny/Dockerfile
git commit -m "feat(#1B fase 1): GI op GertiTicket::TimeAccountingSince (leitura de time_accounting)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 2 — Sidecar: cursor + cliente GI + reconciliação + fechamento

### Task 2: Migration `gerti.consumption_sync_cursor` + modelo ORM

**Files:**
- Create: `apps/sidecar/alembic/versions/0013_consumption_sync_cursor.py`
- Create: `apps/sidecar/src/gerti_sidecar/models/sync_cursor.py`
- Modify: `apps/sidecar/src/gerti_sidecar/models/__init__.py` (exportar `ConsumptionSyncCursor`)
- Test: `apps/sidecar/tests/test_model_sync_cursor.py`

- [ ] **Step 1: Confirmar a revisão head atual**

Run: `cd apps/sidecar && ls alembic/versions/ | sort | tail -3`
Expected: a última é `0012_portal_user_role.py`. Se for outra, ajuste `down_revision` abaixo para a head real.

- [ ] **Step 2: Escrever a migration** (tabela operacional, SEM RLS por tenant; acessada pelo caminho admin/BYPASSRLS)

```python
# apps/sidecar/alembic/versions/0013_consumption_sync_cursor.py
"""consumption_sync_cursor — watermark do pull de time_accounting (Spec #1B)

Revision ID: 0013_consumption_sync_cursor
Revises: 0012_portal_user_role
Create Date: 2026-06-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_consumption_sync_cursor"
down_revision: str | None = "0012_portal_user_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consumption_sync_cursor",
        sa.Column(
            "znuny_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.znuny_instance.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "last_time_accounting_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="gerti",
    )
    # Operacional, não-tenant: NÃO habilita RLS. Só o caminho admin
    # (gerti_admin_user, BYPASSRLS, dono do DDL) lê/escreve. gerti_app não
    # precisa de grant (o worker usa o engine admin para o cursor).


def downgrade() -> None:
    op.drop_table("consumption_sync_cursor", schema="gerti")
```

- [ ] **Step 3: Escrever o modelo ORM**

```python
# apps/sidecar/src/gerti_sidecar/models/sync_cursor.py
"""ConsumptionSyncCursor — watermark do pull de time_accounting (Spec #1B)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class ConsumptionSyncCursor(Base):
    __tablename__ = "consumption_sync_cursor"

    znuny_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.znuny_instance.id"), primary_key=True
    )
    last_time_accounting_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Exportar no `models/__init__.py`**

Adicionar `ConsumptionSyncCursor` ao import e ao `__all__` seguindo o padrão existente do arquivo (ex.: `from gerti_sidecar.models.sync_cursor import ConsumptionSyncCursor`).

- [ ] **Step 5: Escrever o teste do modelo** (testcontainers aplica o init SQL + as migrations? Os testes usam o schema de `infra/compose/postgres/init/001_*.sql` — confirme em `conftest.py` se a tabela precisa existir lá também; se os testes criam o schema via metadata, basta o modelo. Veja como `test_model_tenant_branding.py` faz e espelhe.)

```python
# apps/sidecar/tests/test_model_sync_cursor.py
from __future__ import annotations

import uuid

import pytest

from gerti_sidecar.models import ConsumptionSyncCursor, ZnunyInstance


@pytest.mark.asyncio
async def test_cursor_roundtrip(session):
    inst = ZnunyInstance(
        name="i", base_url="http://z", db_dsn_secret_ref="x",
        webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool",
    )
    session.add(inst)
    await session.flush()
    cur = ConsumptionSyncCursor(znuny_instance_id=inst.id, last_time_accounting_id=42)
    session.add(cur)
    await session.flush()
    got = await session.get(ConsumptionSyncCursor, inst.id)
    assert got is not None and got.last_time_accounting_id == 42
```

> **Nota:** se o `conftest`/testcontainers cria tabelas a partir de `Base.metadata`, o modelo basta. Se aplica as migrations Alembic, a migration 0013 cobre. Verifique qual mecanismo o repo usa (ver `apps/sidecar/tests/conftest.py`) e garanta que a tabela exista no schema de teste — se for via init SQL `001_*.sql`, NÃO precisa editar (o teste usa metadata). Rode o teste para confirmar.

- [ ] **Step 6: Rodar + gate**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_model_sync_cursor.py -q && uv run ruff check . && uv run mypy src`
Expected: passa; gate limpo.

- [ ] **Step 7: Commit**

```bash
git add apps/sidecar/alembic/versions/0013_consumption_sync_cursor.py apps/sidecar/src/gerti_sidecar/models/sync_cursor.py apps/sidecar/src/gerti_sidecar/models/__init__.py apps/sidecar/tests/test_model_sync_cursor.py
git commit -m "feat(#1B fase 2): migration + modelo consumption_sync_cursor (watermark)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3: Cliente GI `time_accounting_since`

**Files:**
- Modify: `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py`
- Test: `apps/sidecar/tests/test_znuny_ticket_timeaccounting.py`

- [ ] **Step 1: Escrever o teste** (mock de `_post`)

```python
# apps/sidecar/tests/test_znuny_ticket_timeaccounting.py
from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket


@pytest.mark.asyncio
async def test_time_accounting_since_maps(monkeypatch):
    async def fake_post(route, body):
        assert route == "/TimeAccounting/Since"
        assert body["SinceId"] == 10
        assert body["Limit"] == 500
        return {
            "Entries": [
                {"Id": 11, "TicketId": 19, "ArticleId": 50, "TimeUnit": "30", "Created": "2026-06-08 10:00:00"},
                {"Id": 12, "TicketId": 19, "ArticleId": 51, "TimeUnit": "15", "Created": "2026-06-08 11:00:00"},
            ],
            "MaxId": 12,
        }

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    page = await znuny_ticket.time_accounting_since(since_id=10, limit=500)
    assert page.max_id == 12
    assert len(page.entries) == 2
    assert page.entries[0].id == 11
    assert page.entries[0].ticket_id == 19
    assert page.entries[0].time_unit == 30.0
    assert page.entries[1].article_id == 51
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd apps/sidecar && uv run pytest tests/test_znuny_ticket_timeaccounting.py -q`
Expected: FAIL (`time_accounting_since` inexistente).

- [ ] **Step 3: Implementar** (adicionar ao `znuny_ticket.py`; incluir no `__all__`)

```python
# adicionar aos dataclasses do topo de znuny_ticket.py:
@dataclass(frozen=True)
class TimeEntry:
    id: int
    ticket_id: int
    article_id: int | None
    time_unit: float
    created: str


@dataclass(frozen=True)
class TimeAccountingPage:
    entries: list[TimeEntry]
    max_id: int


# adicionar a função (perto das outras), e incluir "TimeEntry","TimeAccountingPage",
# "time_accounting_since" no __all__:
async def time_accounting_since(*, since_id: int, limit: int = 500) -> TimeAccountingPage:
    data = await _post("/TimeAccounting/Since", {"SinceId": since_id, "Limit": limit})
    rows = data.get("Entries") or []
    entries = [
        TimeEntry(
            id=int(r["Id"]),
            ticket_id=int(r["TicketId"]),
            article_id=(int(r["ArticleId"]) if r.get("ArticleId") not in (None, "", 0, "0") else None),
            time_unit=float(r.get("TimeUnit") or 0),
            created=str(r.get("Created") or ""),
        )
        for r in rows
        if r.get("Id") is not None
    ]
    return TimeAccountingPage(entries=entries, max_id=int(data.get("MaxId") or since_id))
```

- [ ] **Step 4: Rodar + gate**

Run: `cd apps/sidecar && uv run pytest tests/test_znuny_ticket_timeaccounting.py -q && uv run ruff check . && uv run mypy src`
Expected: 1 passed; gate limpo.

- [ ] **Step 5: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py apps/sidecar/tests/test_znuny_ticket_timeaccounting.py
git commit -m "feat(#1B fase 2): cliente GI time_accounting_since

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4: `reconciliation_service.py` (conversão + idempotência + cursor + RLS)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/reconciliation_service.py`
- Test: `apps/sidecar/tests/test_reconciliation_service.py`

**Contexto de dependências (assinaturas reais a usar):**
- `RecordConsumption(contract_id, occurred_at, source_kind, source_ref, billable_minutes, recorded_by, webhook_event_id=None, billable_amount_brl=0.0, service_id=None)` e `ConsumptionService(session).record(data)` (idempotente por `webhook_event_id`) — em `domain/consumption_service.py`.
- `tenant_session_scope(tenant_id, *, factory=None)` e `AdminSessionLocal` — em `db.py`.
- `Contract` tem `.type` (`ContractType`), `.unit_price_brl`, `.tenant_id`. `TicketContractLink` tem `.znuny_ticket_id`, `.contract_id`, `.tenant_id`. `ConsumptionSyncCursor` (Task 2).

- [ ] **Step 1: Escrever os testes** (RLS real via testcontainers; GI injetado)

```python
# apps/sidecar/tests/test_reconciliation_service.py
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.domain.reconciliation_service import ReconciliationService, NS_TIMEACCOUNTING
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import (
    ConsumptionEvent, ConsumptionSyncCursor, Contract, TicketContractLink, Tenant, ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType
from gerti_sidecar.db import tenant_session_scope


async def _seed(session):
    inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
                         webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
    session.add(inst); await session.flush()
    t = Tenant(legal_name="Acme", trade_name="Acme", document="1",
               znuny_customer_id="ACME", znuny_instance_id=inst.id, subdomain="acme")
    session.add(t); await session.flush()
    hb = Contract(tenant_id=t.id, code="HB", type=ContractType.hour_bank,
                  starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                  initial_hours=100, created_by="seed")
    cb = Contract(tenant_id=t.id, code="CB", type=ContractType.credit_brl,
                  starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                  initial_amount_brl=10000, unit_price_brl=200, created_by="seed")
    session.add_all([hb, cb]); await session.flush()
    # ticket 19 -> hour_bank ; ticket 20 -> credit_brl
    session.add(TicketContractLink(znuny_ticket_id=19, contract_id=hb.id, tenant_id=t.id, linked_by_rule="seed"))
    session.add(TicketContractLink(znuny_ticket_id=20, contract_id=cb.id, tenant_id=t.id, linked_by_rule="seed"))
    session.add(ConsumptionSyncCursor(znuny_instance_id=inst.id, last_time_accounting_id=0))
    await session.commit()
    return inst, t, hb, cb


def _gi_with(entries):
    class _GI:
        async def time_accounting_since(self, *, since_id, limit=500):
            page = [e for e in entries if e.id > since_id][:limit]
            return znuny_ticket.TimeAccountingPage(
                entries=page, max_id=max([e.id for e in page], default=since_id))
    return _GI()


@pytest.mark.asyncio
async def test_reconcile_converts_and_is_idempotent(engine, app_session_factory, session, monkeypatch):
    inst, t, hb, cb = await _seed(session)
    monkeypatch.setattr(db, "AdminSessionLocal",
                        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    entries = [
        znuny_ticket.TimeEntry(id=101, ticket_id=19, article_id=50, time_unit=30.0, created="2026-06-08 10:00:00"),
        znuny_ticket.TimeEntry(id=102, ticket_id=20, article_id=60, time_unit=60.0, created="2026-06-08 11:00:00"),
        znuny_ticket.TimeEntry(id=103, ticket_id=999, article_id=70, time_unit=15.0, created="2026-06-08 12:00:00"),  # sem vínculo
    ]
    svc = ReconciliationService(gi=_gi_with(entries))
    n = await svc.reconcile()
    assert n == 2  # ticket 999 ignorado (sem vínculo)

    # idempotência: re-run não cria novos eventos
    n2 = await svc.reconcile()
    assert n2 == 0

    # verifica conversão sob o tenant
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        rows = (await s.execute(select(ConsumptionEvent).order_by(ConsumptionEvent.id))).scalars().all()
        assert len(rows) == 2
        hb_ev = next(r for r in rows if r.contract_id == hb.id)
        cb_ev = next(r for r in rows if r.contract_id == cb.id)
        assert float(hb_ev.billable_minutes) == 30.0
        assert float(hb_ev.billable_amount_brl) == 0.0   # hour_bank: sem BRL
        assert float(cb_ev.billable_minutes) == 60.0
        assert float(cb_ev.billable_amount_brl) == 200.0  # 60min/60 * 200 = 200
        # webhook_event_id determinístico
        assert hb_ev.webhook_event_id == uuid.uuid5(NS_TIMEACCOUNTING, "znuny:timeaccounting:101")

    # cursor avançou
    async with db.AdminSessionLocal() as a:
        cur = await a.get(ConsumptionSyncCursor, inst.id)
        assert cur.last_time_accounting_id == 103
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_reconciliation_service.py -q`
Expected: FAIL (`reconciliation_service` inexistente).

- [ ] **Step 3: Implementar o serviço**

```python
# apps/sidecar/src/gerti_sidecar/domain/reconciliation_service.py
"""Reconcilia time_accounting do Znuny → gerti.consumption_event (Spec #1B).

Leitura cross-tenant (AdminSessionLocal/BYPASSRLS) de vínculos+contratos+cursor;
escrita por-tenant (tenant_session_scope, RLS-subject) via ConsumptionService.
Idempotência determinística por uuid5 sobre o id do lançamento. O débito de saldo
é automático (balance() soma por tipo). closed_value/saas/service_count recebem o
evento mas o balance() não os afeta por tempo.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections import defaultdict

from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.models import Contract, ConsumptionSyncCursor, TicketContractLink, ZnunyInstance
from gerti_sidecar.models.enums import ContractType

# Namespace fixo p/ derivar webhook_event_id determinístico do id do lançamento.
NS_TIMEACCOUNTING = uuid.UUID("6f1d2b1e-0000-4b1b-9b1b-7e57acc00000")

_CREDIT_TYPES = (ContractType.credit_brl, ContractType.credit_shared)


def _time_unit_to_minutes() -> float:
    raw = os.environ.get("TIME_UNIT_TO_MINUTES", "1")
    try:
        return float(raw)
    except ValueError:
        return 1.0


def _parse_dt(s: str) -> dt.datetime:
    # Znuny create_time: 'YYYY-MM-DD HH:MM:SS' (sem tz) → assume UTC.
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.UTC)
    except (ValueError, TypeError):
        return dt.datetime.now(dt.UTC)


class ReconciliationService:
    def __init__(self, gi) -> None:
        self._gi = gi  # módulo/obj com time_accounting_since(since_id, limit)

    async def reconcile(self, *, limit: int = 500) -> int:
        """Puxa lançamentos novos e grava consumption_events. Retorna nº gravado."""
        if db.AdminSessionLocal is None:
            raise RuntimeError("AdminSessionLocal não inicializado — chame init_db()")

        # 1) cursor (admin/BYPASSRLS). MVP: um único znuny_instance.
        async with db.AdminSessionLocal() as admin:
            inst_id = await admin.scalar(select(ZnunyInstance.id).limit(1))
            if inst_id is None:
                return 0
            cursor = await admin.get(ConsumptionSyncCursor, inst_id)
            since_id = cursor.last_time_accounting_id if cursor is not None else 0

        # 2) pull
        page = await self._gi.time_accounting_since(since_id=since_id, limit=limit)
        if not page.entries:
            return 0

        # 3) leitura cross-tenant: ticket -> (contract, tenant)
        ticket_ids = {e.ticket_id for e in page.entries}
        async with db.AdminSessionLocal() as admin:
            links = (
                await admin.execute(
                    select(TicketContractLink).where(
                        TicketContractLink.znuny_ticket_id.in_(ticket_ids)
                    )
                )
            ).scalars().all()
            link_by_ticket = {l.znuny_ticket_id: l for l in links}
            contract_ids = {l.contract_id for l in links}
            contracts = (
                await admin.execute(select(Contract).where(Contract.id.in_(contract_ids)))
            ).scalars().all()
            contract_by_id = {c.id: c for c in contracts}

        factor = _time_unit_to_minutes()

        # 4) agrupar por tenant e gravar (RLS-subject)
        by_tenant: dict[uuid.UUID, list] = defaultdict(list)
        for e in page.entries:
            link = link_by_ticket.get(e.ticket_id)
            if link is None:
                continue  # ticket sem contrato → ignora
            by_tenant[link.tenant_id].append((e, link))

        written = 0
        for tenant_id, items in by_tenant.items():
            async with db.tenant_session_scope(tenant_id) as s:
                svc = ConsumptionService(s)
                for e, link in items:
                    contract = contract_by_id.get(link.contract_id)
                    if contract is None:
                        continue
                    minutes = float(e.time_unit) * factor
                    amount = 0.0
                    if contract.type in _CREDIT_TYPES:
                        amount = round((minutes / 60.0) * float(contract.unit_price_brl or 0), 2)
                    await svc.record(
                        RecordConsumption(
                            contract_id=link.contract_id,
                            occurred_at=_parse_dt(e.created),
                            source_kind="ticket_work",
                            source_ref=f"znuny:article:{e.article_id}" if e.article_id else f"znuny:ticket:{e.ticket_id}",
                            billable_minutes=minutes,
                            recorded_by="worker:reconcile",
                            billable_amount_brl=amount,
                            webhook_event_id=uuid.uuid5(NS_TIMEACCOUNTING, f"znuny:timeaccounting:{e.id}"),
                        )
                    )
                    written += 1

        # 5) avança cursor (admin/BYPASSRLS) p/ o MaxId puxado
        async with db.AdminSessionLocal() as admin:
            cursor = await admin.get(ConsumptionSyncCursor, inst_id)
            if cursor is None:
                cursor = ConsumptionSyncCursor(znuny_instance_id=inst_id, last_time_accounting_id=page.max_id)
                admin.add(cursor)
            else:
                cursor.last_time_accounting_id = page.max_id
                cursor.updated_at = dt.datetime.now(dt.UTC)
            await admin.commit()

        return written
```

- [ ] **Step 4: Rodar + gate**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_reconciliation_service.py -q && uv run ruff check . && uv run mypy src`
Expected: passa; gate limpo. (Se mypy reclamar do param `gi` sem tipo, anote `gi: object` ou um Protocol mínimo; não mude o comportamento.)

- [ ] **Step 5: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/domain/reconciliation_service.py apps/sidecar/tests/test_reconciliation_service.py
git commit -m "feat(#1B fase 2): reconciliation_service (tempo→consumption_event, idempotente, RLS)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 5: `cycle_closer.py` (fecha ciclos vencidos por tenant)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/cycle_closer.py`
- Test: `apps/sidecar/tests/test_cycle_closer.py`

**Contexto:** `CycleService(session).close(cycle_id)` fecha só `kind=closing` + `status=open` (senão `CycleError`). `ContractCycle` tem `.id, .contract_id, .kind (CycleKind), .period_end (date), .status (CycleStatus)`. `Contract.tenant_id` dá o tenant. Enums: `CycleKind.closing`, `CycleStatus.open`/`closed`.

- [ ] **Step 1: Escrever o teste**

```python
# apps/sidecar/tests/test_cycle_closer.py
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.domain.cycle_closer import CycleCloser
from gerti_sidecar.models import Contract, ContractCycle, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus


@pytest.mark.asyncio
async def test_closes_only_due_open_closing_cycles(engine, app_session_factory, session, monkeypatch):
    inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
                         webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
    session.add(inst); await session.flush()
    t = Tenant(legal_name="Acme", trade_name="Acme", document="1",
               znuny_customer_id="ACME", znuny_instance_id=inst.id, subdomain="acme")
    session.add(t); await session.flush()
    c = Contract(tenant_id=t.id, code="HB", type=ContractType.hour_bank,
                 starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                 initial_hours=100, created_by="seed")
    session.add(c); await session.flush()
    due = ContractCycle(contract_id=c.id, tenant_id=t.id, kind=CycleKind.closing,
                        period_start=dt.date(2026, 1, 1), period_end=dt.date(2026, 1, 31),
                        status=CycleStatus.open)
    future = ContractCycle(contract_id=c.id, tenant_id=t.id, kind=CycleKind.closing,
                           period_start=dt.date(2099, 1, 1), period_end=dt.date(2099, 1, 31),
                           status=CycleStatus.open)
    session.add_all([due, future]); await session.commit()
    monkeypatch.setattr(db, "AdminSessionLocal",
                        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    closed = await CycleCloser().close_due_cycles(today=dt.date(2026, 6, 8))
    assert closed == 1  # só o vencido

    async with db.AdminSessionLocal() as a:
        d = await a.get(ContractCycle, due.id)
        f = await a.get(ContractCycle, future.id)
        assert d.status == CycleStatus.closed
        assert f.status == CycleStatus.open

    # idempotente
    assert await CycleCloser().close_due_cycles(today=dt.date(2026, 6, 8)) == 0
```

> **Nota:** confirme os campos reais de `ContractCycle` (especialmente se `tenant_id` existe na tabela — pelo modelo de #1C ele existe). Se a criação exigir outros campos NOT NULL, espelhe o que `test_cycle_service.py` faz ao montar um ciclo.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_cycle_closer.py -q`
Expected: FAIL (`cycle_closer` inexistente).

- [ ] **Step 3: Implementar**

```python
# apps/sidecar/src/gerti_sidecar/domain/cycle_closer.py
"""Fecha ciclos de fechamento vencidos, por tenant (Spec #1B).

Leitura cross-tenant (admin/BYPASSRLS) dos ciclos open+closing com period_end < hoje;
fecho sob tenant_session_scope (RLS-subject) via CycleService.close (reuso #1C).
Idempotente: um ciclo já fechado não é re-selecionado.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.errors import CycleError
from gerti_sidecar.models import ContractCycle
from gerti_sidecar.models.enums import CycleKind, CycleStatus


class CycleCloser:
    async def close_due_cycles(self, *, today: dt.date | None = None) -> int:
        if db.AdminSessionLocal is None:
            raise RuntimeError("AdminSessionLocal não inicializado — chame init_db()")
        day = today or dt.datetime.now(dt.UTC).date()

        async with db.AdminSessionLocal() as admin:
            rows = (
                await admin.execute(
                    select(ContractCycle.id, ContractCycle.tenant_id).where(
                        ContractCycle.kind == CycleKind.closing,
                        ContractCycle.status == CycleStatus.open,
                        ContractCycle.period_end < day,
                    )
                )
            ).all()

        closed = 0
        for cycle_id, tenant_id in rows:
            async with db.tenant_session_scope(tenant_id) as s:
                try:
                    await CycleService(s).close(cycle_id)
                    closed += 1
                except CycleError:
                    # corrida/estado inesperado: pula, não derruba o lote
                    continue
        return closed
```

> **Nota:** se `ContractCycle` NÃO tiver coluna `tenant_id` (caso o #1C escope o ciclo só via contract→tenant), troque o SELECT para juntar com `Contract` e obter `Contract.tenant_id`. Verifique o modelo `models/cycle.py` antes de implementar.

- [ ] **Step 4: Rodar + gate**

Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_cycle_closer.py -q && uv run ruff check . && uv run mypy src`
Expected: passa; gate limpo.

- [ ] **Step 5: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/domain/cycle_closer.py apps/sidecar/tests/test_cycle_closer.py
git commit -m "feat(#1B fase 2): cycle_closer (fecha ciclos vencidos por tenant, idempotente)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6: Grep-guard — domínio #1B não escreve no schema znuny

**Files:**
- Test: `apps/sidecar/tests/test_consumo_no_direct_znuny.py`

- [ ] **Step 1: Escrever o guard** (espelha o guard do #1E)

```python
# apps/sidecar/tests/test_consumo_no_direct_znuny.py
"""Spec #0: leitura de tempo no Znuny SÓ via GI; sem SQL direto no schema znuny."""

from __future__ import annotations

import pathlib

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "gerti_sidecar"
_FILES = [
    _SRC / "domain" / "reconciliation_service.py",
    _SRC / "domain" / "cycle_closer.py",
    _SRC / "jobs" / "worker.py",
]
_FORBIDDEN = ('"public.', "'public.", '"znuny.', "'znuny.", "time_accounting")


def test_no_direct_znuny_schema_access():
    for f in _FILES:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8").lower()
        for needle in _FORBIDDEN:
            assert needle.lower() not in text, f"{f.name} acessa schema/tabela znuny diretamente: {needle}"
```

- [ ] **Step 2: Rodar** (worker.py ainda não existe → o `if not f.exists()` cobre; reconciliation/cycle_closer não citam `time_accounting`)

Run: `cd apps/sidecar && uv run pytest tests/test_consumo_no_direct_znuny.py -q`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add apps/sidecar/tests/test_consumo_no_direct_znuny.py
git commit -m "test(#1B fase 2): grep-guard — consumo só fala com Znuny via GI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 3 — Worker: job loop + serviço compose

### Task 7: Settings (intervalos) + `jobs/worker.py`

**Files:**
- Modify: `apps/sidecar/src/gerti_sidecar/config.py` (campos novos)
- Create: `apps/sidecar/src/gerti_sidecar/jobs/__init__.py` (vazio)
- Create: `apps/sidecar/src/gerti_sidecar/jobs/worker.py`
- Test: `apps/sidecar/tests/test_worker_tick.py`

- [ ] **Step 1: Adicionar campos ao `Settings`** (`config.py`, na seção de logging/extra)

```python
    # worker de consumo (#1B) -----------------------------------------
    reconcile_interval_seconds: int = 120
    time_unit_to_minutes: float = 1.0
```
(O `_time_unit_to_minutes()` do reconciliation_service lê direto de `os.environ`; manter o campo no Settings documenta a var e permite override em testes. Não é necessário ligar os dois agora.)

- [ ] **Step 2: Escrever o teste do "tick"** (uma iteração isolada, sem loop infinito)

```python
# apps/sidecar/tests/test_worker_tick.py
from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.jobs import worker


@pytest.mark.asyncio
async def test_tick_calls_reconcile_and_daily_close(monkeypatch):
    calls = {"reconcile": 0, "close": 0}

    class FakeRecon:
        def __init__(self, gi): pass
        async def reconcile(self): calls["reconcile"] += 1; return 0

    class FakeCloser:
        async def close_due_cycles(self): calls["close"] += 1; return 0

    monkeypatch.setattr(worker, "ReconciliationService", FakeRecon)
    monkeypatch.setattr(worker, "CycleCloser", FakeCloser)

    state = worker.WorkerState(last_close_date=None)
    # primeira tick: reconcilia + fecha (novo dia)
    await worker.tick(state, today=dt.date(2026, 6, 8))
    assert calls == {"reconcile": 1, "close": 1}
    assert state.last_close_date == dt.date(2026, 6, 8)
    # segunda tick no mesmo dia: só reconcilia
    await worker.tick(state, today=dt.date(2026, 6, 8))
    assert calls == {"reconcile": 2, "close": 1}
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd apps/sidecar && uv run pytest tests/test_worker_tick.py -q`
Expected: FAIL (`jobs.worker` inexistente).

- [ ] **Step 4: Implementar o worker**

```python
# apps/sidecar/src/gerti_sidecar/jobs/__init__.py
```
(arquivo vazio)

```python
# apps/sidecar/src/gerti_sidecar/jobs/worker.py
"""Worker de consumo/fechamento (Spec #1B). Entrypoint do serviço sidecar-worker.

Loop asyncio: reconcilia consumo a cada RECONCILE_INTERVAL_SECONDS; fecha ciclos
vencidos 1×/dia. Cada iteração é isolada (try/except + log); nunca derruba o processo.
Idempotente → seguro reiniciar a qualquer momento.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt

import structlog

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.cycle_closer import CycleCloser
from gerti_sidecar.domain.reconciliation_service import ReconciliationService
from gerti_sidecar.integrations import znuny_ticket

log = structlog.get_logger()


@dataclasses.dataclass
class WorkerState:
    last_close_date: dt.date | None = None


async def tick(state: WorkerState, *, today: dt.date | None = None) -> None:
    """Uma iteração: reconcilia sempre; fecha ciclos 1×/dia."""
    day = today or dt.datetime.now(dt.UTC).date()
    try:
        n = await ReconciliationService(gi=znuny_ticket).reconcile()
        if n:
            log.info("reconcile.done", events=n)
    except Exception as exc:  # noqa: BLE001 — worker nunca pode morrer
        log.warning("reconcile.error", error=str(exc))

    if state.last_close_date != day:
        try:
            closed = await CycleCloser().close_due_cycles()
            state.last_close_date = day
            if closed:
                log.info("cycles.closed", count=closed)
        except Exception as exc:  # noqa: BLE001
            log.warning("close_cycles.error", error=str(exc))


async def run() -> None:
    settings = get_settings()
    db.init_db(settings)
    state = WorkerState()
    log.info("worker.start", interval=settings.reconcile_interval_seconds)
    try:
        while True:
            await tick(state)
            await asyncio.sleep(settings.reconcile_interval_seconds)
    finally:
        await db.dispose_db()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Rodar + gate**

Run: `cd apps/sidecar && uv run pytest tests/test_worker_tick.py -q && uv run ruff check . && uv run mypy src`
Expected: 2 passed; gate limpo.

- [ ] **Step 6: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/config.py apps/sidecar/src/gerti_sidecar/jobs/ apps/sidecar/tests/test_worker_tick.py
git commit -m "feat(#1B fase 3): jobs/worker.py (loop reconcile + close diário) + settings

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 8: Serviço compose `sidecar-worker`

**Files:**
- Modify: `docker-compose.yml` (novo serviço após `sidecar`)

- [ ] **Step 1: Adicionar o serviço** (espelha o bloco `sidecar`, troca command + tira porta/healthcheck HTTP)

Inserir logo após o serviço `sidecar` (depois do bloco `healthcheck` dele, antes do `portal`):

```yaml
  # ───────────────────────────────────────────────────────────────────
  #  Worker de consumo/fechamento (Spec #1B) — profile `gerti`.
  #  Mesma imagem do sidecar, command próprio. Reconcilia time_accounting
  #  do Znuny → consumption_event (idempotente) e fecha ciclos vencidos.
  # ───────────────────────────────────────────────────────────────────
  sidecar-worker:
    profiles: ["gerti"]
    build: { context: ./apps/sidecar, target: prod }
    image: ground-control/sidecar:${GERTI_SIDECAR_VERSION:-dev}
    restart: unless-stopped
    depends_on:
      postgres:        { condition: service_healthy }
      sidecar-migrate: { condition: service_completed_successfully }
    networks: [data, edge, app]
    environment:
      ENVIRONMENT: production
      DATABASE_URL: postgresql+asyncpg://gerti_sidecar:${GERTI_SIDECAR_DB_PASSWORD:-}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-znuny}
      LOG_LEVEL: INFO
      SESSION_SECRET: ${GERTI_SESSION_SECRET:-}
      DATABASE_ADMIN_URL: postgresql+asyncpg://gerti_admin_user:${GERTI_ADMIN_DB_PASSWORD:-}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-znuny}
      ZNUNY_WS_URL: ${ZNUNY_WS_URL:-}
      ZNUNY_WS_TOKEN: ${ZNUNY_WS_TOKEN:-}
      ZNUNY_ADMIN_WS_URL: ${ZNUNY_ADMIN_WS_URL:-}
      ZNUNY_TICKET_WS_URL: ${ZNUNY_TICKET_WS_URL:-}
      RECONCILE_INTERVAL_SECONDS: ${RECONCILE_INTERVAL_SECONDS:-120}
      TIME_UNIT_TO_MINUTES: ${TIME_UNIT_TO_MINUTES:-1}
    command: ["python", "-m", "gerti_sidecar.jobs.worker"]
```

- [ ] **Step 2: Validar o compose** (sem profile não aparece; com profile sim)

Run: `docker compose config --services | grep -c sidecar-worker` → Expected: `0`
Run: `docker compose --profile gerti config --services | grep -c sidecar-worker` → Expected: `1`

> **Nota:** confirme que a imagem expõe `python` no PATH no target `prod` (o sidecar roda via uv; o worker usa o mesmo interpretador). Se o `python` do venv não estiver no PATH do container, troque o command para `["uv","run","python","-m","gerti_sidecar.jobs.worker"]` (mesmo padrão do `sidecar-migrate`, que usa `uv run`). Prefira `uv run` se houver qualquer dúvida — é o que já funciona no `sidecar-migrate`.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(#1B fase 3): serviço compose sidecar-worker (profile gerti)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 4 — Deploy + docs + e2e

### Task 9: Runbook em `OPS.md`

**Files:**
- Modify: `.ia/OPS.md` (nova seção "Deploy do worker de consumo/cobrança (Spec #1B)")

- [ ] **Step 1: Escrever o runbook** (espelha a seção #1E), cobrindo:
  - Pré-req: nenhuma env nova obrigatória (deriva de `ZNUNY_ADMIN_WS_URL`); opcionais `RECONCILE_INTERVAL_SECONDS`, `TIME_UNIT_TO_MINUTES` em `.env.prod`.
  - `ssh gc 'cd ~/ground-control && git pull'`; `DC="docker compose --env-file .env --env-file .env.prod --profile gerti"`.
  - Rebuild `znuny-web` (op GI nova; perl -c gate) + recria `znuny-web`/`znuny-daemon`.
  - Reimport idempotente do `GertiTicket` **com `--name`** (a op nova entra no mesmo webservice; `Admin::WebService::Add` falha se já existe → usar update: `bin/otrs.Console.pl Admin::WebService::List | grep -qi GertiTicket && bin/otrs.Console.pl Admin::WebService::Update --name GertiTicket --source-path /opt/otrs/webservices/GertiTicket.yml || bin/otrs.Console.pl Admin::WebService::Add --name GertiTicket --source-path /opt/otrs/webservices/GertiTicket.yml`). **Importante:** documentar o `Update` para webservice já existente (diferente do #1E que só fazia Add).
  - `$DC build sidecar` → `$DC up -d sidecar-migrate` (aplica migration 0013) — na verdade `sidecar-migrate` roda no `up`; garantir que rodou (Exit 0).
  - `$DC up -d sidecar sidecar-worker` → `$DC ps` (worker `Up`).
  - e2e em prod (ver Task 11).
  - Rollback: `$DC stop sidecar-worker` (reconciliação para; nada destrutivo). **NUNCA** `make reset`.

- [ ] **Step 2: Commit**

```bash
git add .ia/OPS.md
git commit -m "docs(#1B): runbook de deploy do worker de consumo/cobrança

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 10: `ARCHITECTURE.md` + `INTEGRATION.md`

**Files:**
- Modify: `.ia/ARCHITECTURE.md` (subseção do worker de consumo + fluxo time_accounting→consumption_event)
- Modify: `.ia/INTEGRATION.md` (tabela (e): linhas #1B como **Pronto, gateado; deploy per runbook**; registrar a op `TimeAccountingSince`, o `sidecar-worker`, o `consumption_sync_cursor`)

- [ ] **Step 1: Editar os dois** com o estado real (sem "deployado" antes da Task 11 rodar). Atualizar a linha `Billing/consumo (#1B)` de "Não iniciado" → **Pronto, gateado; deploy per runbook**.

- [ ] **Step 2: Commit**

```bash
git add .ia/ARCHITECTURE.md .ia/INTEGRATION.md
git commit -m "docs(#1B): ARCHITECTURE + INTEGRATION — worker de consumo (TimeAccountingSince, cursor)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 11: Gate final + e2e (local e prod)

- [ ] **Step 1: Gate sidecar completo**

Run: `cd apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q`
Expected: tudo verde (inclui os testes novos das Tasks 2-7).

- [ ] **Step 2: e2e local vivo** (stack de pé com profile gerti, como no #1E):
  - Garantir `znuny-web` rebuildado + `GertiTicket` reimportado (com a op nova) + `sidecar`/`sidecar-worker` up.
  - Num ticket vinculado (criar via #1E se preciso), lançar TimeUnits: `docker compose exec -T znuny-web su otrs -s /bin/bash -c "cd /opt/otrs && bin/otrs.Console.pl Admin::Ticket::... "` — OU inserir uma linha de time accounting via a UI de agente. Mais simples p/ o e2e: usar a API nativa `TicketAccountTime` se exposta, ou registrar tempo ao criar um artigo de agente. **Caminho recomendado:** adicionar um artigo de agente com TimeUnit (a UI do agente registra em `time_accounting`).
  - Forçar uma reconciliação imediata (sem esperar o intervalo): `docker compose exec -T -w /app sidecar-worker /app/.venv/bin/python -c "import asyncio; from gerti_sidecar.config import get_settings; from gerti_sidecar import db; from gerti_sidecar.jobs.worker import WorkerState, tick; db.init_db(get_settings()); asyncio.run(tick(WorkerState()))"` (ou rodar `reconcile()` direto).
  - Verificar `consumption_event` criado (psql) e o saldo debitado: `GET /v1/dashboard` ou `GET /v1/contracts/{id}` mostra `saldo` menor / `consumed_percent` maior.

- [ ] **Step 3: e2e em prod** (após deploy — Tasks 9): mesma prova contra a VPS (`ssh gc`), tenant Aurora; lançar TimeUnits num ticket vinculado, aguardar/forçar uma tick do worker, conferir `consumption_event` + saldo debitado, limpar throwaway. Confirmar serviços anteriores intactos.

- [ ] **Step 4: Commit final** (se houver ajustes do e2e):
```bash
git commit -am "fix(#1B): ajustes do e2e vivo

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (cobertura da spec)

- **D-1B-1 escopo (consumo + fechamento)** → Tasks 4 (consumo), 5 (fechamento). ✅
- **D-1B-2 pull via GI** → Task 1 (op `TimeAccountingSince`) + 3 (cliente) + 4 (reconcile). ✅
- **D-1B-3 worker dedicado** → Tasks 7 (loop) + 8 (serviço compose). ✅
- **D-1B-4 conversão uniforme + preço crédito** → Task 4 (`_CREDIT_TYPES`, `minutes/60*unit_price`; demais reusam `balance()`). ✅
- **D-1B-5 fonte `time_accounting` + idempotência uuid5 + cursor** → Task 1 (fonte), 4 (`uuid5(NS_TIMEACCOUNTING,...)` + cursor), 2 (tabela cursor). ✅
- **Segurança §3:** escrita por-tenant (`tenant_session_scope` em 4 e 5), leitura cross-tenant BYPASSRLS, grep-guard (Task 6), reuso intocado de ConsumptionService/CycleService. ✅
- **Dados §4:** migration cursor (Task 2); sem outras alterações de schema. ✅
- **Testes §5:** Tasks 2-7 (sidecar), 1 (perl -c no build), 11 (gate + e2e). ✅
- **Deploy §6:** Tasks 9-10 (runbook+docs), 11 (e2e). ✅

**Pontos a confirmar na execução (sinalizados inline, não placeholders):** mecanismo do conftest (metadata vs migrations) p/ a tabela cursor (Task 2 Step 5); presença de `tenant_id` em `ContractCycle` (Task 5 — senão join com Contract); `python` vs `uv run python` no command do worker (Task 8 Step 2 — preferir `uv run`); unidade real de `time_unit` no Znuny (premissa minutos, env `TIME_UNIT_TO_MINUTES`); e o caminho exato p/ registrar TimeUnits no e2e (Task 11). Todos verificáveis no gate/e2e.
```
