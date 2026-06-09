# Spec #1J — Time Tracker do Agente Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao agente um cronômetro por ticket (start/pause/resume/stop) no Console (apps/admin), na lista e no detalhe; no stop, lançar o tempo (com ajuste+nota) como uma linha `time_accounting` no Znuny via GI — que o #1B já reconcilia em consumo e débito de saldo.

**Architecture:** 3 ops GI novas no webservice `GertiTicket` (`TimeAccountingAdd` embrulhando o nativo `TicketAccountTime`; `AgentTicketSearch`/`AgentTicketGet` para a visão de agente sem escopo de customer). No sidecar: tabela operacional `gerti.agent_timer` (cross-tenant, BYPASSRLS), `timer_service` (start/pause/resume/stop + cálculo de tempo), router `/v1/admin/timer/*` + busca/detalhe de agente, todos sob `get_admin_session`. No app admin: `/atendimento` (lista + timer inline) e `/atendimento/[id]` (detalhe + card de timer), conduzidos por UX. Reusa #1B sem alterá-lo.

**Tech Stack:** Znuny 7.2.3 (Perl/GI, `TicketAccountTime`/`UserLookup`/`TicketSearch`), FastAPI + SQLAlchemy 2 async + Alembic (sidecar), Nuxt 3 + Nuxt UI (apps/admin), pytest/testcontainers + vitest. Spec: `docs/superpowers/specs/2026-06-09-spec-1j-time-tracker-agente-design.md`.

**Convenções de gate:** sidecar `cd apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q`; Znuny `perl -c` no build; `make test` (24) intacto; admin `cd apps/admin && npx nuxi typecheck && npx vitest run`. Commits `feat(#1J ...)` terminando com `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## FASE 1 — Znuny: 3 ops GI no `GertiTicket`

### Task 1: `TimeAccountingAdd.pm` (escreve time_accounting)

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingAdd.pm`

- [ ] **Step 1: Escrever o módulo** (embrulha `TicketAccountTime`; resolve UserID do login)

```perl
# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingAdd.pm
# --
# Gerti — custom GI op (Spec #1J). Wraps native Ticket::TicketAccountTime so the
# agent time-tracker (via sidecar) can log a time_accounting entry. Resolves the
# Znuny UserID from the agent login. Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiTicket::TimeAccountingAdd;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData IsNumber);

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
        ErrorCode => 'TimeAccountingAdd.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(TicketID AgentLogin TimeUnit)) {
        return $Self->ReturnError(
            ErrorCode => 'TimeAccountingAdd.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }
    if ( !IsNumber( $D->{TimeUnit} ) || $D->{TimeUnit} <= 0 ) {
        return $Self->ReturnError(
            ErrorCode => 'TimeAccountingAdd.BadTimeUnit', ErrorMessage => 'TimeUnit must be > 0',
        );
    }

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $UserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    if ( !$UserID ) {
        return $Self->ReturnError(
            ErrorCode => 'TimeAccountingAdd.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');
    # ArticleID is optional; native API accepts time accounted to the ticket.
    my $OK = $TicketObject->TicketAccountTime(
        TicketID  => $D->{TicketID},
        ArticleID => $D->{ArticleID} || undef,
        TimeUnit  => $D->{TimeUnit},
        UserID    => $UserID,
    );
    if ( !$OK ) {
        return $Self->ReturnError(
            ErrorCode => 'TimeAccountingAdd.AccountError', ErrorMessage => 'TicketAccountTime failed',
        );
    }

    return { Success => 1, Data => { OK => 1, UserID => $UserID } };
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

- [ ] **Step 2: Commit** (o `perl -c` roda no build da Task 4)

```bash
git add znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingAdd.pm
git commit -m "feat(#1J fase 1): GI op TimeAccountingAdd (embrulha TicketAccountTime)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2: `AgentTicketSearch.pm` + `AgentTicketGet.pm`

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketSearch.pm`
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketGet.pm`

- [ ] **Step 1: Escrever `AgentTicketSearch.pm`** (busca cross-cliente p/ agente)

```perl
# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketSearch.pm
# Busca de tickets para o agente (sem escopo de customer). Spec #1J.
package Kernel::GenericInterface::Operation::GertiTicket::AgentTicketSearch;

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
        ErrorCode => 'AgentTicketSearch.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    my %Search = ( Result => 'ARRAY', Limit => 50, UserID => 1, OrderBy => 'Down', SortBy => 'Age' );
    # Fulltext em número/título; filtro opcional por CustomerID.
    if ( IsStringWithData( $D->{Query} ) ) {
        # Busca por número exato OU título (fulltext do Znuny usa %...%).
        $Search{Title} = '%' . $D->{Query} . '%';
    }
    $Search{CustomerID} = $D->{CustomerID} if IsStringWithData( $D->{CustomerID} );
    $Search{TicketNumber} = $D->{Number} if IsStringWithData( $D->{Number} );

    my @TicketIDs = $TicketObject->TicketSearch(%Search);

    my @Tickets;
    for my $ID (@TicketIDs) {
        my %T = $TicketObject->TicketGet( TicketID => $ID, UserID => 1 );
        next if !%T;
        push @Tickets, {
            TicketID     => $ID,
            TicketNumber => $T{TicketNumber},
            Title        => $T{Title},
            State        => $T{State},
            CustomerID   => $T{CustomerID},
            Owner        => $T{Owner},
            Created      => $T{Created},
        };
    }
    return { Success => 1, Data => { Tickets => \@Tickets } };
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

- [ ] **Step 2: Escrever `AgentTicketGet.pm`** (detalhe p/ agente, sem guarda de posse por CustomerID)

```perl
# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketGet.pm
# Detalhe de ticket para o agente (staff). Spec #1J.
package Kernel::GenericInterface::Operation::GertiTicket::AgentTicketGet;

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
        ErrorCode => 'AgentTicketGet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    return $Self->ReturnError(
        ErrorCode => 'AgentTicketGet.MissingParameter', ErrorMessage => 'TicketID missing!',
    ) if !IsStringWithData( $D->{TicketID} );

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');
    my %T = $TicketObject->TicketGet( TicketID => $D->{TicketID}, DynamicFields => 1, UserID => 1 );
    return $Self->ReturnError(
        ErrorCode => 'AgentTicketGet.NotFound', ErrorMessage => 'ticket not found',
    ) if !%T;

    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my @ArticleList = $ArticleObject->ArticleList( TicketID => $D->{TicketID} );
    my @Articles;
    for my $Meta (@ArticleList) {
        my $Backend = $ArticleObject->BackendForArticle( %{$Meta} );
        my %A = $Backend->ArticleGet( %{$Meta}, DynamicFields => 0 );
        push @Articles, {
            ArticleID  => $A{ArticleID},
            From       => $A{From},
            SenderType => $A{SenderType},
            Subject    => $A{Subject},
            Body       => $A{Body},
            CreateTime => $A{CreateTime},
        };
    }

    return {
        Success => 1,
        Data    => {
            TicketID     => $D->{TicketID},
            TicketNumber => $T{TicketNumber},
            Title        => $T{Title},
            State        => $T{State},
            Priority     => $T{Priority},
            CustomerID   => $T{CustomerID},
            Owner        => $T{Owner},
            Created      => $T{Created},
            Articles     => \@Articles,
        },
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

- [ ] **Step 3: Commit**

```bash
git add znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketSearch.pm znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketGet.pm
git commit -m "feat(#1J fase 1): GI ops AgentTicketSearch + AgentTicketGet

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3: Registrar as 3 ops no `GertiTicket.yml`

**Files:**
- Modify: `znuny/webservices/GertiTicket.yml`

- [ ] **Step 1: Adicionar as 3 operações + rotas** (sob `Provider.Operation` e `RouteOperationMapping`)

Operações:
```yaml
    TimeAccountingAdd:
      Description: Log a time_accounting entry for an agent (Spec #1J)
      Type: GertiTicket::TimeAccountingAdd
    AgentTicketSearch:
      Description: Agent-side ticket search (no customer scope)
      Type: GertiTicket::AgentTicketSearch
    AgentTicketGet:
      Description: Agent-side ticket detail
      Type: GertiTicket::AgentTicketGet
```
Rotas:
```yaml
        TimeAccountingAdd:
          RequestMethod:
          - POST
          Route: /TimeAccounting/Add
        AgentTicketSearch:
          RequestMethod:
          - POST
          Route: /Agent/Ticket/Search
        AgentTicketGet:
          RequestMethod:
          - POST
          Route: /Agent/Ticket/Get
```

- [ ] **Step 2: Commit**

```bash
git add znuny/webservices/GertiTicket.yml
git commit -m "feat(#1J fase 1): registra TimeAccountingAdd/AgentTicketSearch/AgentTicketGet no GertiTicket.yml

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4: Bake no Dockerfile + build (gate perl -c)

**Files:**
- Modify: `znuny/Dockerfile` (bloco GertiTicket: +3 COPY e +3 no loop perl -c)

- [ ] **Step 1: Adicionar os COPY + loop** (no bloco GertiTicket, junto às outras ops)

Adicionar 3 linhas COPY:
```dockerfile
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingAdd.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingAdd.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketSearch.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketSearch.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketGet.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketGet.pm
```
E incluir os 3 no loop `perl -c` (a linha `for m in ... TimeAccountingSince ; do` vira):
```dockerfile
    for m in TicketCreate TicketSearch TicketGet TicketReply FormMeta TimeAccountingSince TimeAccountingAdd AgentTicketSearch AgentTicketGet ; do \
```

- [ ] **Step 2: Build** Run: `docker compose build znuny-web 2>&1 | grep -iE "TimeAccountingAdd|AgentTicket|syntax OK|Built|error" | tail -12`
Expected: `TimeAccountingAdd.pm syntax OK`, `AgentTicketSearch.pm syntax OK`, `AgentTicketGet.pm syntax OK`, `Built`.

- [ ] **Step 3: Commit**

```bash
git add znuny/Dockerfile
git commit -m "feat(#1J fase 1): bake das 3 ops GertiTicket no Dockerfile (perl -c gate)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 2 — Sidecar: agent_timer + cliente GI + timer_service + router

### Task 5: Migration + modelo `gerti.agent_timer`

**Files:**
- Create: `apps/sidecar/alembic/versions/0014_agent_timer.py`
- Create: `apps/sidecar/src/gerti_sidecar/models/agent_timer.py`
- Modify: `apps/sidecar/src/gerti_sidecar/models/__init__.py`
- Test: `apps/sidecar/tests/test_model_agent_timer.py`

- [ ] **Step 1: Confirmar head** Run: `cd apps/sidecar && ls alembic/versions/ | sort | tail -2` → esperado `0013_consumption_sync_cursor`. Ajustar `down_revision` se diferente.

- [ ] **Step 2: Migration** (tabela operacional, sem RLS por tenant; índice parcial único de ativo)

```python
# apps/sidecar/alembic/versions/0014_agent_timer.py
"""agent_timer — cronômetro por (agente, ticket) (Spec #1J)

Revision ID: 0014_agent_timer
Revises: 0013_consumption_sync_cursor
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_agent_timer"
down_revision: str | None = "0013_consumption_sync_cursor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_timer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_login", sa.String(), nullable=False),
        sa.Column("znuny_ticket_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),  # running|paused|stopped
        sa.Column("accumulated_seconds", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_started_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.String()),
        sa.Column("committed_time_unit", sa.Numeric(10, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('running','paused','stopped')", name="ck_agent_timer_status"),
        schema="gerti",
    )
    # No máximo UM timer ativo (running/paused) por (agente, ticket).
    op.execute(
        "CREATE UNIQUE INDEX ux_agent_timer_active ON gerti.agent_timer "
        "(agent_login, znuny_ticket_id) WHERE status <> 'stopped'"
    )
    # Operacional/não-tenant: SEM RLS. Dono = gerti_admin_user (caminho admin).


def downgrade() -> None:
    op.drop_index("ux_agent_timer_active", table_name="agent_timer", schema="gerti")
    op.drop_table("agent_timer", schema="gerti")
```

- [ ] **Step 3: Modelo ORM**

```python
# apps/sidecar/src/gerti_sidecar/models/agent_timer.py
"""AgentTimer — cronômetro por (agente, ticket) (Spec #1J)."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class AgentTimer(Base):
    __tablename__ = "agent_timer"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_login: Mapped[str] = mapped_column(String, nullable=False)
    znuny_ticket_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    accumulated_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String)
    committed_time_unit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Exportar** `AgentTimer` em `models/__init__.py` (import + `__all__`, seguindo o padrão).

- [ ] **Step 5: Teste do modelo**

```python
# apps/sidecar/tests/test_model_agent_timer.py
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from gerti_sidecar.models import AgentTimer


@pytest.mark.asyncio
async def test_one_active_timer_per_agent_ticket(session):
    session.add(AgentTimer(agent_login="william", znuny_ticket_id=19, status="running"))
    await session.flush()
    # segundo ativo p/ o mesmo (agente,ticket) → viola o índice parcial único
    session.add(AgentTimer(agent_login="william", znuny_ticket_id=19, status="paused"))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
    # mas dois tickets diferentes podem coexistir
    session.add(AgentTimer(agent_login="william", znuny_ticket_id=19, status="running"))
    session.add(AgentTimer(agent_login="william", znuny_ticket_id=20, status="running"))
    await session.flush()
```

- [ ] **Step 6: Rodar + gate** Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_model_agent_timer.py -q && uv run ruff check . && uv run mypy src` → passa + limpo.

- [ ] **Step 7: Commit**

```bash
git add apps/sidecar/alembic/versions/0014_agent_timer.py apps/sidecar/src/gerti_sidecar/models/agent_timer.py apps/sidecar/src/gerti_sidecar/models/__init__.py apps/sidecar/tests/test_model_agent_timer.py
git commit -m "feat(#1J fase 2): migration + modelo agent_timer (1 ativo por agente/ticket)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6: Cliente GI (3 funções)

**Files:**
- Modify: `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py`
- Test: `apps/sidecar/tests/test_znuny_ticket_agent.py`

- [ ] **Step 1: Teste** (mock de `_post`)

```python
# apps/sidecar/tests/test_znuny_ticket_agent.py
from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket


@pytest.mark.asyncio
async def test_time_accounting_add(monkeypatch):
    captured = {}

    async def fake_post(route, body):
        captured["route"] = route
        captured["body"] = body
        return {"OK": 1, "UserID": 7}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    await znuny_ticket.time_accounting_add(
        znuny_ticket_id=19, agent_login="william", time_unit=24.0, note="ok"
    )
    assert captured["route"] == "/TimeAccounting/Add"
    assert captured["body"]["TicketID"] == 19
    assert captured["body"]["AgentLogin"] == "william"
    assert captured["body"]["TimeUnit"] == 24.0


@pytest.mark.asyncio
async def test_agent_search(monkeypatch):
    async def fake_post(route, body):
        assert route == "/Agent/Ticket/Search"
        return {"Tickets": [{"TicketID": 19, "TicketNumber": "n", "Title": "t",
                             "State": "open", "CustomerID": "AURORA", "Owner": "william",
                             "Created": "2026-06-09 10:00:00"}]}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    rows = await znuny_ticket.agent_search(query="impr", customer_id=None)
    assert rows[0].znuny_ticket_id == 19
    assert rows[0].customer_id == "AURORA"
```

- [ ] **Step 2: Rodar e ver falhar** Run: `cd apps/sidecar && uv run pytest tests/test_znuny_ticket_agent.py -q` → FAIL.

- [ ] **Step 3: Implementar** (dataclasses + 3 funções; incluir no `__all__`)

```python
# adicionar aos dataclasses do znuny_ticket.py:
@dataclass(frozen=True)
class AgentTicketSummary:
    znuny_ticket_id: int
    ticket_number: str
    title: str
    state: str
    customer_id: str
    owner: str
    created: str


# 3 funções (incluir nomes no __all__):
async def time_accounting_add(
    *, znuny_ticket_id: int, agent_login: str, time_unit: float, note: str | None = None
) -> None:
    payload: dict[str, Any] = {
        "TicketID": znuny_ticket_id,
        "AgentLogin": agent_login,
        "TimeUnit": time_unit,
    }
    if note:
        payload["Note"] = note
    await _post("/TimeAccounting/Add", payload)


async def agent_search(*, query: str | None, customer_id: str | None) -> list[AgentTicketSummary]:
    body: dict[str, Any] = {}
    if query:
        body["Query"] = query
    if customer_id:
        body["CustomerID"] = customer_id
    data = await _post("/Agent/Ticket/Search", body)
    rows = data.get("Tickets") or []
    return [
        AgentTicketSummary(
            znuny_ticket_id=int(r["TicketID"]),
            ticket_number=str(r.get("TicketNumber") or ""),
            title=str(r.get("Title") or ""),
            state=str(r.get("State") or ""),
            customer_id=str(r.get("CustomerID") or ""),
            owner=str(r.get("Owner") or ""),
            created=str(r.get("Created") or ""),
        )
        for r in rows
        if r.get("TicketID") is not None
    ]


async def agent_get(*, znuny_ticket_id: int) -> dict[str, Any]:
    return await _post("/Agent/Ticket/Get", {"TicketID": znuny_ticket_id})
```

- [ ] **Step 4: Rodar + gate** Run: `cd apps/sidecar && uv run pytest tests/test_znuny_ticket_agent.py -q && uv run ruff check . && uv run mypy src` → passa.

- [ ] **Step 5: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py apps/sidecar/tests/test_znuny_ticket_agent.py
git commit -m "feat(#1J fase 2): cliente GI time_accounting_add + agent_search + agent_get

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 7: `timer_service.py` (start/pause/resume/stop)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/timer_service.py`
- Test: `apps/sidecar/tests/test_timer_service.py`

**Contexto:** opera sob a sessão admin (BYPASSRLS) — o teste injeta uma `AsyncSession` direta (sem RLS, como `session`). O serviço recebe a sessão e o cliente GI. `now` é injetável para testar elapsed sem `Date.now`.

- [ ] **Step 1: Testes**

```python
# apps/sidecar/tests/test_timer_service.py
from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.domain.timer_service import TimerService, TimerError
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import AgentTimer


class _GI:
    def __init__(self): self.calls = []
    async def time_accounting_add(self, *, znuny_ticket_id, agent_login, time_unit, note=None):
        self.calls.append((znuny_ticket_id, agent_login, time_unit, note))


def _t(s): return dt.datetime(2026, 6, 9, 10, 0, s, tzinfo=dt.UTC)


@pytest.mark.asyncio
async def test_start_pause_resume_stop(session):
    gi = _GI()
    svc = TimerService(session, gi)
    t = await svc.start(agent_login="will", znuny_ticket_id=19, now=_t(0))
    assert t.status == "running"
    # start de novo é idempotente (mesmo timer)
    t2 = await svc.start(agent_login="will", znuny_ticket_id=19, now=_t(5))
    assert t2.id == t.id
    await svc.pause(t.id, now=_t(30))         # +30s
    t = await session.get(AgentTimer, t.id)
    assert t.status == "paused" and t.accumulated_seconds == 30
    await svc.resume(t.id, now=_t(40))
    await svc.stop(t.id, now=_t(100), adjust_minutes=None, note="feito")  # +60s → 90s total = 1.5min
    t = await session.get(AgentTimer, t.id)
    assert t.status == "stopped"
    assert gi.calls and gi.calls[0][0] == 19 and gi.calls[0][1] == "will"
    assert abs(float(gi.calls[0][2]) - 1.5) < 1e-6     # 90s = 1.5 min
    assert float(t.committed_time_unit) == 1.5


@pytest.mark.asyncio
async def test_stop_with_adjust_minutes(session):
    gi = _GI()
    svc = TimerService(session, gi)
    t = await svc.start(agent_login="will", znuny_ticket_id=20, now=_t(0))
    await svc.stop(t.id, now=_t(50), adjust_minutes=15.0, note=None)
    assert abs(float(gi.calls[0][2]) - 15.0) < 1e-6    # usa o ajuste, não o real


@pytest.mark.asyncio
async def test_stop_keeps_unstopped_if_gi_fails(session):
    class _BadGI:
        async def time_accounting_add(self, **kw):
            raise znuny_ticket.ZnunyUnavailable("down")
    svc = TimerService(session, _BadGI())
    t = await svc.start(agent_login="will", znuny_ticket_id=21, now=_t(0))
    with pytest.raises(znuny_ticket.ZnunyUnavailable):
        await svc.stop(t.id, now=_t(60), adjust_minutes=None, note=None)
    t = await session.get(AgentTimer, t.id)
    assert t.status != "stopped"   # sem perda: continua ativo p/ re-tentar
```

- [ ] **Step 2: Rodar e ver falhar** Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_timer_service.py -q` → FAIL.

- [ ] **Step 3: Implementar**

```python
# apps/sidecar/src/gerti_sidecar/domain/timer_service.py
"""Cronômetro do agente (Spec #1J): start/pause/resume/stop + cálculo de tempo.

Opera sob a sessão admin (BYPASSRLS — o agente é cross-tenant). pause/resume só
acumulam; stop calcula o total, lança em time_accounting via GI (com ajuste
opcional) e SÓ então marca stopped (sem perda nem relançamento). `now` é
injetável p/ testes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import AgentTimer


class TimerError(Exception):
    """Estado inválido do timer (->409/404)."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _round_minutes(seconds: float) -> float:
    m = Decimal(seconds) / Decimal(60)
    return float(m.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class TimerService:
    def __init__(self, session: AsyncSession, gi) -> None:
        self._session = session
        self._gi = gi

    async def start(self, *, agent_login: str, znuny_ticket_id: int,
                    now: dt.datetime | None = None) -> AgentTimer:
        now = now or _now()
        existing = (
            await self._session.execute(
                select(AgentTimer).where(
                    AgentTimer.agent_login == agent_login,
                    AgentTimer.znuny_ticket_id == znuny_ticket_id,
                    AgentTimer.status != "stopped",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing  # idempotente
        t = AgentTimer(
            agent_login=agent_login, znuny_ticket_id=znuny_ticket_id,
            status="running", accumulated_seconds=0, last_started_at=now,
        )
        self._session.add(t)
        await self._session.flush()
        return t

    async def _get(self, timer_id: uuid.UUID) -> AgentTimer:
        t = await self._session.get(AgentTimer, timer_id)
        if t is None:
            raise TimerError("timer inexistente")
        return t

    async def pause(self, timer_id: uuid.UUID, *, now: dt.datetime | None = None) -> AgentTimer:
        now = now or _now()
        t = await self._get(timer_id)
        if t.status == "running" and t.last_started_at is not None:
            t.accumulated_seconds += int((now - t.last_started_at).total_seconds())
        t.status = "paused"
        t.last_started_at = None
        t.updated_at = now
        await self._session.flush()
        return t

    async def resume(self, timer_id: uuid.UUID, *, now: dt.datetime | None = None) -> AgentTimer:
        now = now or _now()
        t = await self._get(timer_id)
        if t.status == "stopped":
            raise TimerError("timer já encerrado")
        t.status = "running"
        t.last_started_at = now
        t.updated_at = now
        await self._session.flush()
        return t

    async def stop(self, timer_id: uuid.UUID, *, now: dt.datetime | None = None,
                   adjust_minutes: float | None = None, note: str | None = None) -> AgentTimer:
        now = now or _now()
        t = await self._get(timer_id)
        if t.status == "stopped":
            raise TimerError("timer já encerrado")
        total = t.accumulated_seconds
        if t.status == "running" and t.last_started_at is not None:
            total += int((now - t.last_started_at).total_seconds())
        minutes = adjust_minutes if adjust_minutes is not None else _round_minutes(total)
        if minutes <= 0:
            minutes = 0.01  # nunca lança 0 (TimeAccountingAdd exige > 0)
        # Lança no Znuny PRIMEIRO; só marca stopped se o GI confirmar.
        await self._gi.time_accounting_add(
            znuny_ticket_id=t.znuny_ticket_id, agent_login=t.agent_login,
            time_unit=float(minutes), note=note,
        )
        t.accumulated_seconds = total
        t.status = "stopped"
        t.last_started_at = None
        t.note = note
        t.committed_time_unit = Decimal(str(minutes))
        t.updated_at = now
        await self._session.flush()
        return t
```

- [ ] **Step 4: Rodar + gate** Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_timer_service.py -q && uv run ruff check . && uv run mypy src` → passa. (Se mypy reclamar de `gi` sem tipo, use `gi: Any`.)

- [ ] **Step 5: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/domain/timer_service.py apps/sidecar/tests/test_timer_service.py
git commit -m "feat(#1J fase 2): timer_service (start/pause/resume/stop, lança no Znuny só após GI)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 8: Router `/v1/admin/timer/*` + busca/detalhe de agente

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/routers/admin_timer.py`
- Modify: `apps/sidecar/src/gerti_sidecar/main.py` (registrar)
- Test: `apps/sidecar/tests/test_admin_timer_router.py`

- [ ] **Step 1: Teste** (auth admin + ciclo start→stop; GI mockado no módulo)

```python
# apps/sidecar/tests/test_admin_timer_router.py
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app


@pytest.mark.asyncio
async def test_timer_lifecycle_requires_admin(engine, app_session_factory, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    async def fake_add(**kw):
        return None

    monkeypatch.setattr(znuny_ticket, "time_accounting_add", fake_add)
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # sem gsid_adm → 401
        assert (await c.post("/v1/admin/timer/start", json={"znuny_ticket_id": 19})).status_code == 401
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post("/v1/admin/timer/start", json={"znuny_ticket_id": 19})
        assert r.status_code == 201
        tid = r.json()["id"]
        assert (await c.post(f"/v1/admin/timer/pause", json={"timer_id": tid})).status_code == 200
        assert (await c.post(f"/v1/admin/timer/resume", json={"timer_id": tid})).status_code == 200
        s = await c.post("/v1/admin/timer/stop", json={"timer_id": tid, "adjust_minutes": 10})
        assert s.status_code == 200
        assert s.json()["status"] == "stopped"
        # active list
        a = await c.get("/v1/admin/timer/active")
        assert a.status_code == 200
```

> **Nota:** confirme o nome real do helper de encode da sessão admin em `auth/admin_session.py` (pode ser `encode_admin_session` ou similar) e ajuste o import/uso. Veja `test_admin_*` existentes para o padrão exato de montar o cookie `gsid_adm`.

- [ ] **Step 2: Rodar e ver falhar** Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_admin_timer_router.py -q` → FAIL.

- [ ] **Step 3: Implementar o router**

```python
# apps/sidecar/src/gerti_sidecar/routers/admin_timer.py
"""Timer do agente + busca/detalhe de tickets (Spec #1J). Todos sob get_admin_session.

Caminho admin/BYPASSRLS (agente é cross-tenant). O timer vive em gerti.agent_timer;
o stop lança em time_accounting via GI (→ #1B cobra). A busca junta o contrato
vinculado (ticket_contract_link) por ticket p/ exibir/avisar.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain.timer_service import TimerError, TimerService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.models import AgentTimer, Contract, TicketContractLink

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_factory():
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    return db.AdminSessionLocal


class StartBody(BaseModel):
    znuny_ticket_id: int


class TimerIdBody(BaseModel):
    timer_id: str


class StopBody(BaseModel):
    timer_id: str
    adjust_minutes: float | None = None
    note: str | None = None


class TimerOut(BaseModel):
    id: str
    znuny_ticket_id: int
    status: str
    accumulated_seconds: int
    last_started_at: str | None
    committed_time_unit: float | None


def _out(t: AgentTimer) -> TimerOut:
    return TimerOut(
        id=str(t.id), znuny_ticket_id=t.znuny_ticket_id, status=t.status,
        accumulated_seconds=t.accumulated_seconds,
        last_started_at=t.last_started_at.isoformat() if t.last_started_at else None,
        committed_time_unit=float(t.committed_time_unit) if t.committed_time_unit is not None else None,
    )


@router.post("/timer/start", status_code=201, response_model=TimerOut)
async def start_timer(body: StartBody, admin: AdminSessionPayload = Depends(get_admin_session)) -> TimerOut:
    factory = _admin_factory()
    async with factory() as s:
        t = await TimerService(s, znuny_ticket).start(
            agent_login=admin["agent_login"], znuny_ticket_id=body.znuny_ticket_id
        )
        await s.commit()
        return _out(t)


@router.post("/timer/pause", response_model=TimerOut)
async def pause_timer(body: TimerIdBody, admin: AdminSessionPayload = Depends(get_admin_session)) -> TimerOut:
    factory = _admin_factory()
    async with factory() as s:
        try:
            t = await TimerService(s, znuny_ticket).pause(uuid.UUID(body.timer_id))
        except TimerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await s.commit()
        return _out(t)


@router.post("/timer/resume", response_model=TimerOut)
async def resume_timer(body: TimerIdBody, admin: AdminSessionPayload = Depends(get_admin_session)) -> TimerOut:
    factory = _admin_factory()
    async with factory() as s:
        try:
            t = await TimerService(s, znuny_ticket).resume(uuid.UUID(body.timer_id))
        except TimerError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await s.commit()
        return _out(t)


@router.post("/timer/stop", response_model=TimerOut)
async def stop_timer(body: StopBody, admin: AdminSessionPayload = Depends(get_admin_session)) -> TimerOut:
    factory = _admin_factory()
    async with factory() as s:
        try:
            t = await TimerService(s, znuny_ticket).stop(
                uuid.UUID(body.timer_id), adjust_minutes=body.adjust_minutes, note=body.note
            )
        except TimerError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ZnunyWriteError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ZnunyUnavailable as exc:
            raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
        await s.commit()
        return _out(t)


@router.get("/timer/active")
async def active_timers(admin: AdminSessionPayload = Depends(get_admin_session)) -> list[TimerOut]:
    factory = _admin_factory()
    async with factory() as s:
        rows = (
            await s.execute(
                select(AgentTimer).where(
                    AgentTimer.agent_login == admin["agent_login"],
                    AgentTimer.status != "stopped",
                )
            )
        ).scalars().all()
        return [_out(t) for t in rows]


@router.get("/tickets")
async def search_tickets(
    q: str | None = None, customer_id: str | None = None,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[dict]:
    try:
        rows = await znuny_ticket.agent_search(query=q, customer_id=customer_id)
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    # junta contrato vinculado por ticket (BYPASSRLS, read-only)
    factory = _admin_factory()
    ids = [r.znuny_ticket_id for r in rows]
    contract_by_ticket: dict[int, dict] = {}
    if ids:
        async with factory() as s:
            links = (
                await s.execute(
                    select(TicketContractLink.znuny_ticket_id, Contract.code, Contract.type)
                    .join(Contract, Contract.id == TicketContractLink.contract_id)
                    .where(TicketContractLink.znuny_ticket_id.in_(ids))
                )
            ).all()
            contract_by_ticket = {tid: {"code": code, "type": str(typ)} for tid, code, typ in links}
    return [
        {
            "znuny_ticket_id": r.znuny_ticket_id, "ticket_number": r.ticket_number,
            "title": r.title, "state": r.state, "customer_id": r.customer_id,
            "owner": r.owner, "created": r.created,
            "contract": contract_by_ticket.get(r.znuny_ticket_id),
        }
        for r in rows
    ]


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: int, admin: AdminSessionPayload = Depends(get_admin_session)) -> dict:
    try:
        detail = await znuny_ticket.agent_get(znuny_ticket_id=ticket_id)
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    factory = _admin_factory()
    async with factory() as s:
        row = (
            await s.execute(
                select(Contract.code, Contract.type)
                .join(TicketContractLink, TicketContractLink.contract_id == Contract.id)
                .where(TicketContractLink.znuny_ticket_id == ticket_id)
            )
        ).first()
        detail["contract"] = {"code": row[0], "type": str(row[1])} if row else None
    return detail
```

- [ ] **Step 4: Registrar no `main.py`** (importar `admin_timer`, `app.include_router(admin_timer.router, prefix=settings.api_v1_prefix)` junto aos outros admin).

- [ ] **Step 5: Rodar + gate** Run: `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_admin_timer_router.py -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src` → passa + limpo.

- [ ] **Step 6: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/routers/admin_timer.py apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/tests/test_admin_timer_router.py
git commit -m "feat(#1J fase 2): router /v1/admin/timer/* + busca/detalhe de tickets do agente

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 9: Grep-guard — domínio #1J não escreve no schema znuny

**Files:**
- Test: `apps/sidecar/tests/test_timer_no_direct_znuny.py`

- [ ] **Step 1: Guard**

```python
# apps/sidecar/tests/test_timer_no_direct_znuny.py
"""Spec #0: tempo/ticket no Znuny SÓ via GI; sem SQL direto no schema znuny."""

from __future__ import annotations

import pathlib

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "gerti_sidecar"
_FILES = [
    _SRC / "domain" / "timer_service.py",
    _SRC / "routers" / "admin_timer.py",
]
_FORBIDDEN = ('"public.', "'public.", '"znuny.', "'znuny.", "from time_accounting", "into time_accounting")


def test_no_direct_znuny_schema_access():
    for f in _FILES:
        text = f.read_text(encoding="utf-8").lower()
        for needle in _FORBIDDEN:
            assert needle.lower() not in text, f"{f.name} acessa schema znuny direto: {needle}"
```

- [ ] **Step 2: Rodar** Run: `cd apps/sidecar && uv run pytest tests/test_timer_no_direct_znuny.py -q` → 1 passed.

- [ ] **Step 3: Commit**

```bash
git add apps/sidecar/tests/test_timer_no_direct_znuny.py
git commit -m "test(#1J fase 2): grep-guard — timer só fala com Znuny via GI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 3 — App admin: /atendimento (lista + detalhe) com timer

> **REQUIRED SUB-SKILL para esta fase:** invocar a skill `frontend-design`. Aceite: o agente entende e opera o timer sem fricção — cronômetro ticando claro, estados running/paused/idle distintos, contrato vinculado/aviso visível, diálogo de stop simples (ajuste + nota → "Lançar"). Reusar Nuxt UI + a identidade Gerti/WAS do Console. Padrões existentes: `apps/admin/server/utils/sidecar.ts` (proxy), `apps/admin/composables/useAdmin.ts`, `apps/admin/middleware/admin-auth.ts`, `apps/admin/pages/index.vue`.

### Task 10: Server proxies do admin (timer + tickets)

**Files:**
- Create: `apps/admin/server/api/admin/timer/start.post.ts`, `pause.post.ts`, `resume.post.ts`, `stop.post.ts`, `active.get.ts`
- Create: `apps/admin/server/api/admin/tickets/index.get.ts`, `[id].get.ts`

- [ ] **Step 1: Criar os proxies** (padrão `sidecarFetch`, repassa `gsid_adm`).

POST (ex. `start.post.ts`):
```ts
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/admin/timer/start', { method: 'POST', body })
  setResponseStatus(event, status)
  return data
})
```
(idem pause/resume/stop trocando o path; o `active.get.ts` e `tickets/index.get.ts`/`[id].get.ts` são GET — repassam querystring via `getQuery(event)` montando o path, ex. `/v1/admin/tickets?q=...`.)

`tickets/index.get.ts`:
```ts
export default defineEventHandler(async (event) => {
  const qp = getQuery(event)
  const search = new URLSearchParams()
  if (qp.q) search.set('q', String(qp.q))
  if (qp.customer_id) search.set('customer_id', String(qp.customer_id))
  const path = '/v1/admin/tickets' + (search.toString() ? `?${search}` : '')
  const { status, data } = await sidecarFetch(event, path)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
```

- [ ] **Step 2: Typecheck** Run: `cd apps/admin && npx nuxi typecheck 2>&1 | tail -20` → sem erros nos arquivos novos (erros pré-existentes em `nuxt.config.ts` são aceitáveis).

- [ ] **Step 3: Commit**

```bash
git add apps/admin/server/api/admin/timer apps/admin/server/api/admin/tickets
git commit -m "feat(#1J fase 3): server proxies admin de timer + tickets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 11: Composable `useTimers` + página `/atendimento` (lista + timer inline)

**Files:**
- Create: `apps/admin/composables/useTimers.ts`
- Create: `apps/admin/pages/atendimento/index.vue`
- Modify: `apps/admin/layouts/default.vue` (ou onde está a nav) — link "Atendimento"

- [ ] **Step 1: Invocar `frontend-design`** e construir.

`useTimers` (estado dos timers ativos + tick local):
- `load()` → `GET /api/admin/timer/active` → mapa `ticketId → timer`.
- `start/pause/resume/stop(...)` → chamam os proxies e atualizam o estado.
- `elapsed(timer)` → segundos = `accumulated_seconds + (status==='running' ? (agora - last_started_at) : 0)`; um `setInterval(1s)` reativo dispara o re-render do display (formata `HH:MM:SS`).

Página `/atendimento` (`definePageMeta({ middleware: 'admin-auth' })`):
- Busca (`UInput` + debounce) → `GET /api/admin/tickets?q=`.
- Linhas: número, assunto, cliente, **contrato** (badge `code`/tipo, ou `⚠ sem contrato` quando `contract===null`), e a célula de **timer**:
  - idle → `▶ Iniciar` (start);
  - running → cronômetro ticando + `⏸` (pause) + `⏹` (stop → abre diálogo);
  - paused → tempo congelado + `pausado` + `⏵` (resume) + `⏹`.
- Diálogo de stop (`UModal`): mostra o tempo, campo **minutos** (default = arredondado) + **nota**, botão **"Lançar"** → `POST stop {timer_id, adjust_minutes, note}` → toast.
- Chip no header: "⏱ N timers ativos" (de `useTimers`).
- Estados vazio/carregando/erro em PT-BR; cores semânticas nunca = cor de marca.

- [ ] **Step 2: Verificação** `cd apps/admin && npx nuxi typecheck && npx eslint pages/atendimento/index.vue composables/useTimers.ts 2>&1 | tail -20` → limpo nos arquivos novos.

- [ ] **Step 3: Commit**

```bash
git add apps/admin/composables/useTimers.ts apps/admin/pages/atendimento/index.vue apps/admin/layouts/default.vue
git commit -m "feat(#1J fase 3): /atendimento — lista de tickets com timer inline + nav

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 12: Página `/atendimento/[id]` (detalhe + card de timer)

**Files:**
- Create: `apps/admin/pages/atendimento/[id].vue`

- [ ] **Step 1: Construir** (skill `frontend-design`):
- `GET /api/admin/tickets/[id]` (SSR). 404 → "chamado não encontrado".
- Cabeçalho: assunto, número, cliente, estado, prioridade, **contrato vinculado/saldo** (ou ⚠ sem contrato).
- **Card de timer em destaque** (cronômetro grande + ⏸/⏵/⏹ conforme estado), reusando `useTimers` (o mesmo timer aparece aqui e na lista, pois o estado é do servidor).
- Thread de artigos (`articles[]`: From, SenderType, Subject, Body, CreateTime) — distinguir cliente vs agente sem cor de marca.
- Diálogo de stop idêntico ao da lista (ajuste + nota → "Lançar").

- [ ] **Step 2: Verificação** `cd apps/admin && npx nuxi typecheck` → limpo nos arquivos novos.

- [ ] **Step 3: Commit**

```bash
git add apps/admin/pages/atendimento/[id].vue
git commit -m "feat(#1J fase 3): /atendimento/[id] — detalhe do ticket + card de timer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 13: Smoke vitest do admin (lógica do timer)

**Files:**
- Create: teste vitest seguindo o harness existente do `apps/admin` (procure `apps/admin/test*`/`vitest.config*`; se houver, espelhe; senão, teste a lógica pura de `useTimers.elapsed`/format).

- [ ] **Step 1: Localizar harness** Run: `ls apps/admin/test* apps/admin/vitest.config* 2>/dev/null; grep -rl vitest apps/admin --include=package.json`.
- [ ] **Step 2: Escrever o smoke** — assert: `elapsed()` soma `accumulated_seconds` + delta quando running; formata `HH:MM:SS`; `showContractWarning` quando `contract===null`. Mockar `$fetch` se precisar.
- [ ] **Step 3: Rodar** `cd apps/admin && npx vitest run 2>&1 | tail -15` → verde.
- [ ] **Step 4: Commit** `git add apps/admin/test* && git commit -m "test(#1J fase 3): smoke da lógica do timer no admin\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"`

---

## FASE 4 — Deploy + docs + e2e

### Task 14: Runbook OPS.md

**Files:** Modify `.ia/OPS.md` (seção "Deploy do time tracker do agente (Spec #1J)").

- [ ] **Step 1: Escrever** (espelha o runbook #1B), cobrindo: `git pull`; rebuild `znuny-web` (3 ops; perl -c) + recria; **Update** do `GertiTicket` (`Admin::WebService::Update --webservice-id <id>` — resolver o id da lista; nunca `--name`); `sidecar-migrate` aplica `0014`; rebuild `sidecar` + `admin`; e2e (logar agente → start → stop → `time_accounting` → worker #1B → saldo debita → limpar); intactness; rollback `$DC stop admin`. **NUNCA** `make reset`.
- [ ] **Step 2: Commit** `git add .ia/OPS.md && git commit -m "docs(#1J): runbook de deploy do time tracker\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"`

### Task 15: ARCHITECTURE + INTEGRATION

**Files:** Modify `.ia/ARCHITECTURE.md` (subseção do time tracker no Console + fluxo timer→time_accounting→#1B) e `.ia/INTEGRATION.md` (tabela (e): linhas #1J **Pronto, gateado; deploy per runbook** — 3 ops GI, `agent_timer`, `/v1/admin/timer/*`, páginas `/atendimento`).

- [ ] **Step 1: Editar** (factual; não "deployado" antes da Task 16).
- [ ] **Step 2: Commit** `git add .ia/ARCHITECTURE.md .ia/INTEGRATION.md && git commit -m "docs(#1J): ARCHITECTURE + INTEGRATION — time tracker do agente\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"`

### Task 16: Gate final + e2e (local e prod)

- [ ] **Step 1: Gate sidecar** Run: `cd apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q` → tudo verde.
- [ ] **Step 2: Admin** Run: `cd apps/admin && npx nuxi typecheck && npx vitest run` → sem erros nos arquivos novos; vitest verde.
- [ ] **Step 3: e2e local** — stack profile gerti de pé; rebuild `znuny-web` + Update GertiTicket + `sidecar`/`admin` up. Logar como agente (`gsid_adm` via `encode_admin_session`), buscar um ticket Aurora vinculado, `start` → esperar alguns segundos → `stop` com ajuste → conferir a linha `time_accounting` (psql/GI) → forçar uma tick do worker #1B → **saldo debitado** no contrato → limpar throwaway (timer, time_accounting; o consumption_event é append-only).
- [ ] **Step 4: e2e prod** — após deploy (Task 14): mesma prova na VPS, tenant Aurora; limpar. Serviços anteriores intactos.

---

## Self-Review (cobertura da spec)

- **D-1J-1 (superfície admin, lista+detalhe)** → Tasks 11, 12. ✅
- **D-1J-2 (vários simultâneos, 1 por agente/ticket)** → Task 5 (índice parcial único) + 7 (start idempotente). ✅
- **D-1J-3 (commit no stop, ajuste+nota)** → Task 7 (`stop` adjust_minutes/note) + 11/12 (diálogo). ✅
- **D-1J-4 (busca todos + contrato/aviso)** → Task 8 (`/admin/tickets` + join link) + 11/12. ✅
- **D-1J-5 (botão "Lançar", cobrança downstream)** → Task 7 (só lança time_accounting; #1B cobra) + UI "Lançar". ✅
- **D-1J-6 (estado no servidor)** → Task 5 (tabela) + 11 (tick a partir do estado). ✅
- **GI:** TimeAccountingAdd (1), AgentTicketSearch/Get (2), yml (3), bake/perl -c (4). ✅
- **Segurança §3:** get_admin_session (8), BYPASSRLS, GI-only (grep-guard Task 9), stop só após GI (7). ✅
- **Testes §5 / Deploy §6:** Tasks 5-9/13 (testes), 14-16 (deploy+docs+e2e). ✅

**Pontos a confirmar na execução (sinalizados inline):** nome real do helper de sessão admin (`encode_admin_session`?) na Task 8; harness vitest do `apps/admin` (Task 13); local da nav no `apps/admin` (Task 11); tipo de `gi`/`Any` no mypy (Task 7). Todos verificáveis no gate/e2e.
```
