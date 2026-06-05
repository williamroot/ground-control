# Spec #1E — Portal Ticketing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que o cliente abra chamados no portal (com seleção de contrato), liste os seus e veja/responda o detalhe — toda escrita/leitura de ticket no Znuny via um webservice GI custom `GertiTicket`, com o chamado nascendo vinculado a um contrato (`gerti.ticket_contract_link` + DynamicField `GertiContractId`), billing-ready para a #1B.

**Architecture:** Três camadas no padrão já em prod. **Znuny** (`znuny/Custom/`): webservice `GertiTicket` (ops Create/Search/Get/Reply/FormMeta, `AccessToken` fail-closed, espelhando `GertiAdmin`) + DynamicField `GertiContractId`. **Sidecar** (`apps/sidecar`): cliente GI `znuny_ticket.py`, domínio `ticketing_service.py`, routers `tickets.py`/`ticketing_meta.py` (RLS por tenant, escopo por papel #1H, guarda de posse anti-IDOR, anexos multipart). **Portal** (`apps/portal`): páginas `/tickets`, `/tickets/novo` (form página única), `/tickets/[id]`, com server-proxies que repassam o cookie `gsid`. A cobrança/consumo é a próxima spec (#1B) — aqui só o vínculo.

**Tech Stack:** Znuny 7.2.3 (Perl/mod_perl, Generic Interface REST), FastAPI + SQLAlchemy 2 async + httpx + pytest/testcontainers (sidecar), Nuxt 3 SSR + Nuxt UI (portal). Spec: `docs/superpowers/specs/2026-06-05-spec-1e-portal-ticketing-design.md`.

**Convenções de gate (zero-tolerância):**
- Sidecar: `cd apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q` (testcontainers exige Docker).
- Znuny: `perl -I$OTRS_HOME -I$OTRS_HOME/Kernel/cpan-lib -I$OTRS_HOME/Custom -c <módulo>` + smoke vivo via `bin/otrs.Console.pl`.
- Stack base intocada: `make test` (24 asserts) continua verde.
- Commits frequentes, mensagens `feat(#1E ...)`/`test(#1E ...)`, terminando com `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## FASE 0 — Contrato de API congelado (destrava paralelismo Fase 1 ⇄ Fase 2)

### Task 0: Congelar assinaturas do cliente GI + shapes Pydantic

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py` (stub com assinaturas + exceções reusadas)
- Test: `apps/sidecar/tests/test_ticketing_phase0_smoke.py`

- [ ] **Step 1: Escrever o teste de smoke do stub**

```python
# apps/sidecar/tests/test_ticketing_phase0_smoke.py
"""Fase 0: o cliente GI de ticket existe com as assinaturas congeladas."""

from __future__ import annotations

import inspect

from gerti_sidecar.integrations import znuny_ticket


def test_signatures_frozen():
    for name in ("create_ticket", "search_tickets", "get_ticket", "reply_ticket", "form_meta"):
        assert hasattr(znuny_ticket, name), f"falta {name}"
    # reusa as MESMAS exceções do cliente admin (não cria novas hierarquias)
    from gerti_sidecar.integrations.znuny_customer_admin import (
        ZnunyUnavailable,
        ZnunyWriteError,
    )

    assert znuny_ticket.ZnunyUnavailable is ZnunyUnavailable
    assert znuny_ticket.ZnunyWriteError is ZnunyWriteError
    # create_ticket é async
    assert inspect.iscoroutinefunction(znuny_ticket.create_ticket)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd apps/sidecar && uv run pytest tests/test_ticketing_phase0_smoke.py -q`
Expected: FAIL — `ModuleNotFoundError: ...znuny_ticket`.

- [ ] **Step 3: Escrever o stub com as assinaturas congeladas**

```python
# apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py
"""Cliente GI de ticket (Spec #1E). Escrita/leitura de ticket no Znuny via o
webservice custom GertiTicket (mesmo padrão de znuny_customer_admin.py): base
ZNUNY_ADMIN_WS_URL com path /Webservice/GertiTicket; AccessToken = ZNUNY_WS_TOKEN
no corpo JSON. Erros REUSADOS de znuny_customer_admin (ZnunyUnavailable -> 503,
ZnunyWriteError -> 4xx). Corpo preenchido na Task 7; assinaturas congeladas aqui
para a Fase 1 (Znuny) e a Fase 3 (portal) não divergirem.

Convenção de URL: o webservice GertiTicket é servido na MESMA URL base do
GertiAdmin trocando o último segmento. Resolve-se de ZNUNY_TICKET_WS_URL se
presente, senão deriva de ZNUNY_ADMIN_WS_URL trocando '/GertiAdmin' por
'/GertiTicket' (deploy injeta ZNUNY_TICKET_WS_URL explícito na Fase 4).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from gerti_sidecar.integrations.znuny_customer_admin import (
    ZnunyUnavailable,
    ZnunyWriteError,
)

__all__ = [
    "ZnunyUnavailable",
    "ZnunyWriteError",
    "TicketCreated",
    "TicketSummary",
    "TicketDetail",
    "create_ticket",
    "search_tickets",
    "get_ticket",
    "reply_ticket",
    "form_meta",
]

_TIMEOUT = 15.0


@dataclass(frozen=True)
class TicketCreated:
    znuny_ticket_id: int
    ticket_number: str


@dataclass(frozen=True)
class TicketSummary:
    znuny_ticket_id: int
    ticket_number: str
    title: str
    state: str
    created: str
    contract_id: str | None


@dataclass(frozen=True)
class TicketDetail:
    znuny_ticket_id: int
    ticket_number: str
    title: str
    state: str
    priority: str
    created: str
    contract_id: str | None
    customer_id: str
    articles: list[dict[str, Any]]


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    content_base64: str


async def create_ticket(
    *,
    customer_user: str,
    customer_id: str,
    title: str,
    body: str,
    service: str | None,
    type_: str | None,
    priority: str | None,
    contract_id: str,
    attachments: list[Attachment] | None = None,
) -> TicketCreated:
    raise NotImplementedError  # Task 7


async def search_tickets(
    *,
    scope: str,  # "own" | "company"
    customer_user: str,
    customer_id: str,
) -> list[TicketSummary]:
    raise NotImplementedError  # Task 7


async def get_ticket(*, znuny_ticket_id: int, customer_id: str) -> TicketDetail:
    raise NotImplementedError  # Task 7


async def reply_ticket(
    *, znuny_ticket_id: int, customer_user: str, customer_id: str, body: str
) -> None:
    raise NotImplementedError  # Task 7


async def form_meta(*, customer_user: str) -> dict[str, list[dict[str, Any]]]:
    raise NotImplementedError  # Task 7


def _resolve_ticket_endpoint() -> tuple[str, str]:
    explicit = os.environ.get("ZNUNY_TICKET_WS_URL", "")
    if explicit:
        base = explicit
    else:
        base = os.environ.get("ZNUNY_ADMIN_WS_URL", "").replace("/GertiAdmin", "/GertiTicket")
    token = os.environ.get("ZNUNY_WS_TOKEN", "")
    return base, token


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST failure-safe para uma Route do GertiTicket (espelha _post do admin)."""
    base, token = _resolve_ticket_endpoint()
    url = base.rstrip("/") + route
    payload = {"AccessToken": token, **body}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise ZnunyUnavailable(str(exc)) from exc
    if resp.status_code >= 500:
        raise ZnunyUnavailable(f"znuny http {resp.status_code}")
    if resp.status_code >= 400:
        raise ZnunyWriteError(_err(_safe_json(resp)) or f"znuny http {resp.status_code}")
    data = _safe_json(resp)
    if data is None:
        raise ZnunyUnavailable("resposta não-JSON do Znuny")
    if "Error" in data:
        raise ZnunyWriteError(_err(data) or "znuny rejeitou a operação")
    return data


def _safe_json(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _err(data: dict[str, Any] | None) -> str:
    if not data:
        return ""
    e = data.get("Error")
    if isinstance(e, dict):
        return str(e.get("ErrorMessage") or e.get("ErrorCode") or "znuny error")
    return str(e) if e else ""
```

- [ ] **Step 4: Rodar e ver passar + lint/type**

Run: `cd apps/sidecar && uv run pytest tests/test_ticketing_phase0_smoke.py -q && uv run ruff check src/gerti_sidecar/integrations/znuny_ticket.py && uv run mypy src/gerti_sidecar/integrations/znuny_ticket.py`
Expected: 1 passed; ruff/mypy limpos.

- [ ] **Step 5: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py apps/sidecar/tests/test_ticketing_phase0_smoke.py
git commit -m "feat(#1E fase 0): congela assinaturas do cliente GI de ticket (stub)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 1 — Znuny: webservice GertiTicket + DynamicField

> Todas as operações Perl vivem em `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/` e espelham `CustomerCompany/CustomerCompanyAdd.pm` (estrutura `new` + `Run` + `_CheckAccessToken` + `ReturnError`). O token esperado é `GertiAdmin::AccessToken` (REUSADO — o mesmo `ZNUNY_WS_TOKEN`; não há config novo). Verificação por operação = `perl -c` + smoke vivo no container.

### Task 1: Operação `TicketCreate.pm`

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm`

- [ ] **Step 1: Escrever o módulo**

```perl
# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm
# --
# Gerti — custom GI operation (Spec #1E). Wraps native Ticket::TicketCreate +
# Article backend so the portal (via sidecar) can open a customer ticket linked
# to a contract. Writes the contract UUID into DynamicField GertiContractId.
# Upgrade-safe Custom/ overlay (same as GertiAdmin ops).
# --
package Kernel::GenericInterface::Operation::GertiTicket::TicketCreate;

use strict;
use warnings;

use MIME::Base64 qw(decode_base64);
use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData IsArrayRefWithData);

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

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'TicketCreate.MissingParameter',
            ErrorMessage => 'TicketCreate: the request is empty!',
        );
    }
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(CustomerUser CustomerID Title Body ContractId)) {
        if ( !IsStringWithData( $D->{$Needed} ) ) {
            return $Self->ReturnError(
                ErrorCode    => 'TicketCreate.MissingParameter',
                ErrorMessage => "TicketCreate: $Needed is missing!",
            );
        }
    }

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    # Queue: derive from Service if not given. Customer tickets land in the
    # service's default queue; fall back to 'Raw' (Znuny default) if absent.
    my %CreateArgs = (
        Title        => $D->{Title},
        CustomerUser => $D->{CustomerUser},
        CustomerID   => $D->{CustomerID},
        Lock         => 'unlock',
        OwnerID      => 1,
        UserID       => 1,
        StateType    => 'new',
        State        => 'new',
    );
    $CreateArgs{Queue}    = $D->{Queue}    || 'Raw';
    $CreateArgs{Priority} = $D->{Priority} || '3 normal';
    $CreateArgs{Type}     = $D->{Type} if IsStringWithData( $D->{Type} );
    $CreateArgs{Service}  = $D->{Service} if IsStringWithData( $D->{Service} );

    my $TicketID = $TicketObject->TicketCreate(%CreateArgs);
    if ( !$TicketID ) {
        return $Self->ReturnError(
            ErrorCode    => 'TicketCreate.CreateError',
            ErrorMessage => 'TicketCreate: native TicketCreate failed.',
        );
    }

    # Stamp the contract on the ticket (DynamicField GertiContractId).
    my $DFObject      = $Kernel::OM->Get('Kernel::System::DynamicField');
    my $DFBackend     = $Kernel::OM->Get('Kernel::System::DynamicField::Backend');
    my $DFConfig      = $DFObject->DynamicFieldGet( Name => 'GertiContractId' );
    if ( IsHashRefWithData($DFConfig) ) {
        $DFBackend->ValueSet(
            DynamicFieldConfig => $DFConfig,
            ObjectID           => $TicketID,
            Value              => $D->{ContractId},
            UserID             => 1,
        );
    }

    # First (customer-visible) article.
    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my $Backend       = $ArticleObject->BackendForChannel( ChannelName => 'Internal' );
    my @Attachments;
    if ( IsArrayRefWithData( $D->{Attachments} ) ) {
        for my $A ( @{ $D->{Attachments} } ) {
            next if !IsHashRefWithData($A) || !IsStringWithData( $A->{Filename} );
            push @Attachments, {
                Content     => decode_base64( $A->{ContentBase64} // '' ),
                ContentType => $A->{ContentType} || 'application/octet-stream',
                Filename    => $A->{Filename},
            };
        }
    }
    my $ArticleID = $Backend->ArticleCreate(
        TicketID             => $TicketID,
        SenderType           => 'customer',
        IsVisibleForCustomer => 1,
        From                 => $D->{CustomerUser},
        Subject              => $D->{Title},
        Body                 => $D->{Body},
        ContentType          => 'text/plain; charset=utf-8',
        HistoryType          => 'WebRequestCustomer',
        HistoryComment       => 'Gerti portal ticket',
        UserID               => 1,
        ( @Attachments ? ( Attachment => \@Attachments ) : () ),
    );
    if ( !$ArticleID ) {
        return $Self->ReturnError(
            ErrorCode    => 'TicketCreate.ArticleError',
            ErrorMessage => 'TicketCreate: article create failed.',
        );
    }

    my $TicketNumber = $TicketObject->TicketNumberLookup( TicketID => $TicketID );

    return {
        Success => 1,
        Data    => { TicketID => $TicketID, TicketNumber => $TicketNumber },
    };
}

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;
    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAdmin::AccessToken') || '';
    if ( !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected ) {
        return $Self->ReturnError(
            ErrorCode    => 'GertiTicket.AuthFail',
            ErrorMessage => 'GertiTicket: invalid or missing AccessToken.',
        );
    }
    return;
}

1;
```

- [ ] **Step 2: Verificar a sintaxe (perl -c) num container Znuny**

Pré-requisito: imagem Znuny construída. Verificação local sem rebuild — copiar o módulo para um container vivo e checar:
```bash
docker compose cp znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm \
  znuny-web:/opt/otrs/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm
docker compose exec -T znuny-web perl -I/opt/otrs -I/opt/otrs/Kernel/cpan-lib -I/opt/otrs/Custom \
  -c /opt/otrs/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm
```
Expected: `... syntax OK`.

- [ ] **Step 3: Commit**

```bash
git add znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm
git commit -m "feat(#1E fase 1): GI op GertiTicket::TicketCreate (ticket+contrato DynamicField)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2: Operações `TicketSearch.pm` + `TicketGet.pm` (lista + detalhe, com guarda de posse)

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm`
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm`

- [ ] **Step 1: Escrever `TicketSearch.pm`**

```perl
# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm
# Lista tickets do cliente. scope "own" => CustomerUserID; "company" => CustomerID.
package Kernel::GenericInterface::Operation::GertiTicket::TicketSearch;

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
        ErrorCode => 'TicketSearch.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    my $Scope = $D->{Scope} || 'own';
    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    my %Search = ( Result => 'ARRAY', Limit => 200, UserID => 1, OrderBy => 'Down', SortBy => 'Created' );
    if ( $Scope eq 'company' && IsStringWithData( $D->{CustomerID} ) ) {
        $Search{CustomerID} = $D->{CustomerID};
    }
    else {
        $Search{CustomerUserLogin} = $D->{CustomerUser};
    }
    my @TicketIDs = $TicketObject->TicketSearch(%Search);

    my $DFObject  = $Kernel::OM->Get('Kernel::System::DynamicField');
    my $DFConfig  = $DFObject->DynamicFieldGet( Name => 'GertiContractId' );
    my $DFBackend = $Kernel::OM->Get('Kernel::System::DynamicField::Backend');

    my @Tickets;
    for my $ID (@TicketIDs) {
        my %T = $TicketObject->TicketGet( TicketID => $ID, DynamicFields => 1, UserID => 1 );
        next if !%T;
        my $Contract = IsHashRefWithData($DFConfig)
            ? $DFBackend->ValueGet( DynamicFieldConfig => $DFConfig, ObjectID => $ID )
            : undef;
        push @Tickets, {
            TicketID     => $ID,
            TicketNumber => $T{TicketNumber},
            Title        => $T{Title},
            State        => $T{State},
            Created      => $T{Created},
            ContractId   => $Contract,
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

- [ ] **Step 2: Escrever `TicketGet.pm` (com guarda de posse anti-IDOR)**

```perl
# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm
# Detalhe + thread de artigos visíveis ao cliente. Guarda de posse: o ticket
# DEVE pertencer ao CustomerID informado, senão NotFound.
package Kernel::GenericInterface::Operation::GertiTicket::TicketGet;

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
        ErrorCode => 'TicketGet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(TicketID CustomerID)) {
        return $Self->ReturnError(
            ErrorCode => 'TicketGet.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');
    my %T = $TicketObject->TicketGet( TicketID => $D->{TicketID}, DynamicFields => 1, UserID => 1 );

    # Posse: ticket inexistente OU de outra empresa => NotFound (não vaza existência).
    if ( !%T || ( $T{CustomerID} // '' ) ne $D->{CustomerID} ) {
        return $Self->ReturnError(
            ErrorCode => 'TicketGet.NotFound', ErrorMessage => 'ticket not found',
        );
    }

    my $DFObject  = $Kernel::OM->Get('Kernel::System::DynamicField');
    my $DFConfig  = $DFObject->DynamicFieldGet( Name => 'GertiContractId' );
    my $DFBackend = $Kernel::OM->Get('Kernel::System::DynamicField::Backend');
    my $Contract  = IsHashRefWithData($DFConfig)
        ? $DFBackend->ValueGet( DynamicFieldConfig => $DFConfig, ObjectID => $D->{TicketID} )
        : undef;

    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my @ArticleList = $ArticleObject->ArticleList(
        TicketID => $D->{TicketID}, IsVisibleForCustomer => 1,
    );
    my @Articles;
    for my $Meta (@ArticleList) {
        my $Backend = $ArticleObject->BackendForArticle(%{$Meta});
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
            Created      => $T{Created},
            CustomerID   => $T{CustomerID},
            ContractId   => $Contract,
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

- [ ] **Step 3: `perl -c` nas duas operações** (copiar para o container como na Task 1)

Run (para cada arquivo):
```bash
docker compose cp znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm znuny-web:/opt/otrs/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm
docker compose cp znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm znuny-web:/opt/otrs/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm
docker compose exec -T znuny-web bash -lc 'for m in TicketSearch TicketGet; do perl -I/opt/otrs -I/opt/otrs/Kernel/cpan-lib -I/opt/otrs/Custom -c /opt/otrs/Custom/Kernel/GenericInterface/Operation/GertiTicket/$m.pm; done'
```
Expected: `syntax OK` para os dois.

- [ ] **Step 4: Commit**

```bash
git add znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm
git commit -m "feat(#1E fase 1): GI ops GertiTicket::TicketSearch + TicketGet (posse anti-IDOR)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3: Operações `TicketReply.pm` + `FormMeta.pm`

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketReply.pm`
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/FormMeta.pm`

- [ ] **Step 1: Escrever `TicketReply.pm`**

```perl
# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketReply.pm
# Resposta do cliente a um ticket existente. Mesma guarda de posse do TicketGet.
package Kernel::GenericInterface::Operation::GertiTicket::TicketReply;

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
        ErrorCode => 'TicketReply.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(TicketID CustomerUser CustomerID Body)) {
        return $Self->ReturnError(
            ErrorCode => 'TicketReply.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');
    my %T = $TicketObject->TicketGet( TicketID => $D->{TicketID}, UserID => 1 );
    if ( !%T || ( $T{CustomerID} // '' ) ne $D->{CustomerID} ) {
        return $Self->ReturnError(
            ErrorCode => 'TicketReply.NotFound', ErrorMessage => 'ticket not found',
        );
    }

    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my $Backend       = $ArticleObject->BackendForChannel( ChannelName => 'Internal' );
    my $ArticleID = $Backend->ArticleCreate(
        TicketID             => $D->{TicketID},
        SenderType           => 'customer',
        IsVisibleForCustomer => 1,
        From                 => $D->{CustomerUser},
        Subject              => $D->{Subject} || 'Re: ' . ( $T{Title} // '' ),
        Body                 => $D->{Body},
        ContentType          => 'text/plain; charset=utf-8',
        HistoryType          => 'FollowUp',
        HistoryComment       => 'Gerti portal reply',
        UserID               => 1,
    );
    return $Self->ReturnError(
        ErrorCode => 'TicketReply.ArticleError', ErrorMessage => 'reply failed',
    ) if !$ArticleID;

    return { Success => 1, Data => { ArticleID => $ArticleID } };
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

- [ ] **Step 2: Escrever `FormMeta.pm`** (serviços do cliente + prioridades + tipos)

```perl
# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/FormMeta.pm
# Catálogo do formulário: serviços do CustomerUser, prioridades, tipos.
package Kernel::GenericInterface::Operation::GertiTicket::FormMeta;

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
        ErrorCode => 'FormMeta.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    return $Self->ReturnError(
        ErrorCode => 'FormMeta.MissingParameter', ErrorMessage => 'CustomerUser missing!',
    ) if !IsStringWithData( $D->{CustomerUser} );

    # Serviços disponíveis ao cliente (Service::ServiceList do CustomerUser).
    my $ServiceObject = $Kernel::OM->Get('Kernel::System::Service');
    my %ServiceHash   = $ServiceObject->CustomerUserServiceMemberList(
        CustomerUserLogin => $D->{CustomerUser},
        Result            => 'HASH',
        DefaultServices   => 1,
    );
    my @Services = map { { Key => $_, Value => $ServiceHash{$_} } } sort keys %ServiceHash;

    # Prioridades.
    my $PriorityObject = $Kernel::OM->Get('Kernel::System::Priority');
    my %PriorityHash   = $PriorityObject->PriorityList( Valid => 1, UserID => 1 );
    my @Priorities = map { { Key => $_, Value => $PriorityHash{$_} } } sort { $a <=> $b } keys %PriorityHash;

    # Tipos (se Ticket::Type estiver ativo).
    my @Types;
    if ( $Kernel::OM->Get('Kernel::Config')->Get('Ticket::Type') ) {
        my $TypeObject = $Kernel::OM->Get('Kernel::System::Type');
        my %TypeHash   = $TypeObject->TypeList( Valid => 1, UserID => 1 );
        @Types = map { { Key => $_, Value => $TypeHash{$_} } } sort keys %TypeHash;
    }

    return {
        Success => 1,
        Data    => { Services => \@Services, Priorities => \@Priorities, Types => \@Types },
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

- [ ] **Step 3: `perl -c` nas duas** (copiar para o container e checar como na Task 2)

Run:
```bash
for m in TicketReply FormMeta; do docker compose cp znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/$m.pm znuny-web:/opt/otrs/Custom/Kernel/GenericInterface/Operation/GertiTicket/$m.pm; done
docker compose exec -T znuny-web bash -lc 'for m in TicketReply FormMeta; do perl -I/opt/otrs -I/opt/otrs/Kernel/cpan-lib -I/opt/otrs/Custom -c /opt/otrs/Custom/Kernel/GenericInterface/Operation/GertiTicket/$m.pm; done'
```
Expected: `syntax OK` para os dois.

- [ ] **Step 4: Commit**

```bash
git add znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketReply.pm znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/FormMeta.pm
git commit -m "feat(#1E fase 1): GI ops GertiTicket::TicketReply + FormMeta

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4: Webservice `GertiTicket.yml`

**Files:**
- Create: `znuny/webservices/GertiTicket.yml`

- [ ] **Step 1: Escrever o YAML** (espelha `GertiAdmin.yml`)

```yaml
# znuny/webservices/GertiTicket.yml
---
Debugger:
  DebugThreshold: error
  TestMode: '0'
Description: Gerti portal ticketing (#1E) — Create/Search/Get/Reply/FormMeta via GI
FrameworkVersion: 7.2.x
Provider:
  Operation:
    TicketCreate:
      Description: Open a customer ticket linked to a contract (Gerti custom op)
      Type: GertiTicket::TicketCreate
    TicketSearch:
      Description: List customer tickets (own/company)
      Type: GertiTicket::TicketSearch
    TicketGet:
      Description: Ticket detail + customer-visible articles (ownership-guarded)
      Type: GertiTicket::TicketGet
    TicketReply:
      Description: Customer reply to an existing ticket
      Type: GertiTicket::TicketReply
    FormMeta:
      Description: Services/priorities/types for the open-ticket form
      Type: GertiTicket::FormMeta
  Transport:
    Config:
      KeepAlive: ''
      MaxLength: '100000000'
      RouteOperationMapping:
        TicketCreate:
          RequestMethod:
          - POST
          Route: /Ticket
        TicketSearch:
          RequestMethod:
          - POST
          Route: /Ticket/Search
        TicketGet:
          RequestMethod:
          - POST
          Route: /Ticket/Get
        TicketReply:
          RequestMethod:
          - POST
          Route: /Ticket/Reply
        FormMeta:
          RequestMethod:
          - POST
          Route: /FormMeta
    Type: HTTP::REST
RemoteSystem: ''
```

- [ ] **Step 2: Commit**

```bash
git add znuny/webservices/GertiTicket.yml
git commit -m "feat(#1E fase 1): webservice GertiTicket.yml (5 ops, HTTP::REST)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 5: Bake na imagem (Dockerfile) + criação idempotente do DynamicField

**Files:**
- Modify: `znuny/Dockerfile` (após o bloco GertiAdmin, linhas ~141-164)
- Create: `znuny/scripts/ensure-gerti-dynamicfield.pl`

- [ ] **Step 1: Criar o script idempotente de DynamicField**

```perl
# znuny/scripts/ensure-gerti-dynamicfield.pl
# Cria o DynamicField GertiContractId (Text, objeto Ticket) se ainda não existir.
# Idempotente: se já existe, não faz nada. Roda como otrs no deploy.
use strict;
use warnings;
use lib '/opt/otrs';
use lib '/opt/otrs/Kernel/cpan-lib';
use lib '/opt/otrs/Custom';
use Kernel::System::ObjectManager;

local $Kernel::OM = Kernel::System::ObjectManager->new();
my $DFObject = $Kernel::OM->Get('Kernel::System::DynamicField');

my $Existing = $DFObject->DynamicFieldGet( Name => 'GertiContractId' );
if ( $Existing && %{$Existing} ) {
    print "GertiContractId already present — skipping\n";
    exit 0;
}

my $ID = $DFObject->DynamicFieldAdd(
    Name       => 'GertiContractId',
    Label      => 'Contrato Gerti',
    FieldOrder => 9000,
    FieldType  => 'Text',
    ObjectType => 'Ticket',
    Config     => { DefaultValue => '', Link => '' },
    ValidID    => 1,
    UserID     => 1,
);
die "FATAL: could not create GertiContractId DynamicField\n" if !$ID;
print "GertiContractId created (id $ID)\n";
exit 0;
```

- [ ] **Step 2: Adicionar os COPY + perl -c no Dockerfile** (logo após a linha 164, o bloco do GertiAdmin.yml)

Inserir após `RUN chown -R otrs:www-data ${OTRS_HOME}/webservices` (linha 164):

```dockerfile
# ── Custom GI operations for the GertiTicket webservice (#1E). Portal ticketing:
#    open/list/detail/reply linked to a contract. Same Custom/ overlay pattern.
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketReply.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketReply.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/FormMeta.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/FormMeta.pm
RUN set -eux; \
    chown -R otrs:www-data ${OTRS_HOME}/Custom; \
    for m in TicketCreate TicketSearch TicketGet TicketReply FormMeta ; do \
        perl -I${OTRS_HOME} -I${OTRS_HOME}/Kernel/cpan-lib -I${OTRS_HOME}/Custom \
             -c ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/$m.pm ; \
    done

# ── GertiTicket webservice definition (#1E) + DynamicField helper, baked in.
COPY webservices/GertiTicket.yml ${OTRS_HOME}/webservices/GertiTicket.yml
COPY scripts/ensure-gerti-dynamicfield.pl ${OTRS_HOME}/scripts/ensure-gerti-dynamicfield.pl
RUN chown -R otrs:www-data ${OTRS_HOME}/webservices ${OTRS_HOME}/scripts/ensure-gerti-dynamicfield.pl
```

- [ ] **Step 3: Build da imagem (gate: perl -c roda no build)**

Run: `docker compose build znuny-web`
Expected: build conclui; as 5 linhas `... syntax OK` aparecem no log do passo dos módulos GertiTicket.

- [ ] **Step 4: Commit**

```bash
git add znuny/Dockerfile znuny/scripts/ensure-gerti-dynamicfield.pl
git commit -m "feat(#1E fase 1): bake GertiTicket (ops+yml) na imagem + ensure-gerti-dynamicfield.pl

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6: Smoke vivo da Fase 1 (DynamicField + import + TicketCreate real)

**Files:** nenhum (verificação operacional; documenta o comando que a Fase 4 reusa).

- [ ] **Step 1: Subir o znuny rebuildado e criar o DynamicField**

Run:
```bash
docker compose up -d znuny-web znuny-daemon
docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  'cd /opt/otrs && perl scripts/ensure-gerti-dynamicfield.pl'
```
Expected: `GertiContractId created (id N)` (ou `already present` em re-run).

- [ ] **Step 2: Importar o webservice idempotentemente (guard: não tocar auth/admin)**

Run:
```bash
docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  'cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List | grep -qi GertiTicket || \
   bin/otrs.Console.pl Admin::WebService::Add --source-path /opt/otrs/webservices/GertiTicket.yml'
docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  'cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List'
```
Expected: a lista contém `GertiCustomerAuth`, `GertiAdmin` **e** `GertiTicket` (nenhum removido).

- [ ] **Step 3: TicketCreate real via curl interno** (usa o token de `Config.pm`)

Run (substitua `<TOKEN>` pelo `GertiAdmin::AccessToken` real do ambiente; `<CU>` por um customer_user válido — ex.: o admin Aurora do seed):
```bash
docker compose exec -T znuny-web bash -lc 'curl -fsS -X POST \
  -H "content-type: application/json" \
  -d "{\"AccessToken\":\"<TOKEN>\",\"CustomerUser\":\"<CU>\",\"CustomerID\":\"AURORA\",\"Title\":\"smoke 1E\",\"Body\":\"corpo\",\"ContractId\":\"00000000-0000-0000-0000-000000000000\"}" \
  http://127.0.0.1/znuny/nph-genericinterface.pl/Webservice/GertiTicket/Ticket'
```
Expected: JSON `{"TicketID":...,"TicketNumber":"..."}`. Conferir o DynamicField:
```bash
docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  'cd /opt/otrs && bin/otrs.Console.pl Admin::Ticket::Search --dynamic-field GertiContractId=00000000-0000-0000-0000-000000000000 2>/dev/null || true'
```
Limpar o throwaway depois (anotar o TicketID; em dev pode deixar).

- [ ] **Step 4: Commit** (nenhuma mudança de código; pular se não há arquivo. Caso tenha ajustado algum módulo após o smoke, commitar o ajuste com `fix(#1E fase 1): ...`.)

---

## FASE 2 — Sidecar: cliente GI + domínio + endpoints

### Task 7: Implementar o corpo do cliente GI `znuny_ticket.py`

**Files:**
- Modify: `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py`
- Test: `apps/sidecar/tests/test_znuny_ticket_client.py`

- [ ] **Step 1: Escrever os testes (GI mockado via monkeypatch de `_post`)**

```python
# apps/sidecar/tests/test_znuny_ticket_client.py
from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket


@pytest.mark.asyncio
async def test_create_ticket_maps_fields(monkeypatch):
    captured = {}

    async def fake_post(route, body):
        captured["route"] = route
        captured["body"] = body
        return {"TicketID": 42, "TicketNumber": "2026010100001"}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    out = await znuny_ticket.create_ticket(
        customer_user="joe@acme.test",
        customer_id="ACME",
        title="t",
        body="b",
        service="Suporte N1",
        type_="Incidente",
        priority="3 normal",
        contract_id="c-uuid",
        attachments=[znuny_ticket.Attachment("a.txt", "text/plain", "Zm9v")],
    )
    assert out == znuny_ticket.TicketCreated(42, "2026010100001")
    assert captured["route"] == "/Ticket"
    b = captured["body"]
    assert b["CustomerUser"] == "joe@acme.test"
    assert b["ContractId"] == "c-uuid"
    assert b["Attachments"][0]["Filename"] == "a.txt"


@pytest.mark.asyncio
async def test_search_company_scope(monkeypatch):
    async def fake_post(route, body):
        assert route == "/Ticket/Search"
        assert body["Scope"] == "company"
        return {"Tickets": [{"TicketID": 1, "TicketNumber": "n1", "Title": "x",
                             "State": "new", "Created": "2026-01-01 00:00:00",
                             "ContractId": "c1"}]}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    rows = await znuny_ticket.search_tickets(scope="company", customer_user="j", customer_id="ACME")
    assert rows[0].contract_id == "c1"
    assert rows[0].znuny_ticket_id == 1


@pytest.mark.asyncio
async def test_get_ticket_passes_customer_id(monkeypatch):
    async def fake_post(route, body):
        assert route == "/Ticket/Get"
        assert body["CustomerID"] == "ACME"
        return {"TicketID": 7, "TicketNumber": "n", "Title": "t", "State": "open",
                "Priority": "3 normal", "Created": "2026-01-01 00:00:00",
                "CustomerID": "ACME", "ContractId": "c1", "Articles": []}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    d = await znuny_ticket.get_ticket(znuny_ticket_id=7, customer_id="ACME")
    assert d.customer_id == "ACME"
    assert d.articles == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd apps/sidecar && uv run pytest tests/test_znuny_ticket_client.py -q`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Preencher o corpo das 5 funções** (substituir os `raise NotImplementedError`)

```python
# substituir create_ticket:
async def create_ticket(
    *,
    customer_user: str,
    customer_id: str,
    title: str,
    body: str,
    service: str | None,
    type_: str | None,
    priority: str | None,
    contract_id: str,
    attachments: list[Attachment] | None = None,
) -> TicketCreated:
    payload: dict[str, Any] = {
        "CustomerUser": customer_user,
        "CustomerID": customer_id,
        "Title": title,
        "Body": body,
        "ContractId": contract_id,
    }
    if service:
        payload["Service"] = service
    if type_:
        payload["Type"] = type_
    if priority:
        payload["Priority"] = priority
    if attachments:
        payload["Attachments"] = [
            {"Filename": a.filename, "ContentType": a.content_type, "ContentBase64": a.content_base64}
            for a in attachments
        ]
    data = await _post("/Ticket", payload)
    return TicketCreated(int(data["TicketID"]), str(data["TicketNumber"]))


async def search_tickets(
    *, scope: str, customer_user: str, customer_id: str
) -> list[TicketSummary]:
    data = await _post(
        "/Ticket/Search",
        {"Scope": scope, "CustomerUser": customer_user, "CustomerID": customer_id},
    )
    rows = data.get("Tickets") or []
    return [
        TicketSummary(
            znuny_ticket_id=int(r["TicketID"]),
            ticket_number=str(r.get("TicketNumber") or ""),
            title=str(r.get("Title") or ""),
            state=str(r.get("State") or ""),
            created=str(r.get("Created") or ""),
            contract_id=(str(r["ContractId"]) if r.get("ContractId") else None),
        )
        for r in rows
    ]


async def get_ticket(*, znuny_ticket_id: int, customer_id: str) -> TicketDetail:
    data = await _post(
        "/Ticket/Get", {"TicketID": znuny_ticket_id, "CustomerID": customer_id}
    )
    return TicketDetail(
        znuny_ticket_id=int(data["TicketID"]),
        ticket_number=str(data.get("TicketNumber") or ""),
        title=str(data.get("Title") or ""),
        state=str(data.get("State") or ""),
        priority=str(data.get("Priority") or ""),
        created=str(data.get("Created") or ""),
        contract_id=(str(data["ContractId"]) if data.get("ContractId") else None),
        customer_id=str(data.get("CustomerID") or ""),
        articles=list(data.get("Articles") or []),
    )


async def reply_ticket(
    *, znuny_ticket_id: int, customer_user: str, customer_id: str, body: str
) -> None:
    await _post(
        "/Ticket/Reply",
        {
            "TicketID": znuny_ticket_id,
            "CustomerUser": customer_user,
            "CustomerID": customer_id,
            "Body": body,
        },
    )


async def form_meta(*, customer_user: str) -> dict[str, list[dict[str, Any]]]:
    data = await _post("/FormMeta", {"CustomerUser": customer_user})
    return {
        "services": list(data.get("Services") or []),
        "priorities": list(data.get("Priorities") or []),
        "types": list(data.get("Types") or []),
    }
```

- [ ] **Step 4: Rodar e ver passar + gate**

Run: `cd apps/sidecar && uv run pytest tests/test_znuny_ticket_client.py -q && uv run ruff check . && uv run mypy src`
Expected: 3 passed; gate limpo.

- [ ] **Step 5: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py apps/sidecar/tests/test_znuny_ticket_client.py
git commit -m "feat(#1E fase 2): corpo do cliente GI znuny_ticket (create/search/get/reply/form_meta)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 8: Domínio `ticketing_service.py` (seleção de contrato + grava o link)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/ticketing_service.py`
- Test: `apps/sidecar/tests/test_ticketing_service.py`

- [ ] **Step 1: Escrever os testes** (RLS real via testcontainers, GI mockado)

```python
# apps/sidecar/tests/test_ticketing_service.py
from __future__ import annotations

import datetime as dt
import uuid

import pytest

from gerti_sidecar.domain.ticketing_service import (
    NoActiveContract,
    ContractChoiceRequired,
    OpenTicketInput,
    TicketingService,
)
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import Contract, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType
from gerti_sidecar.db import tenant_session_scope


async def _seed_tenant(session, *, n_contracts: int) -> Tenant:
    inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
                         webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
    session.add(inst)
    await session.flush()
    t = Tenant(legal_name="Acme", trade_name="Acme", document="1",
               znuny_customer_id="ACME", znuny_instance_id=inst.id, subdomain="acme")
    session.add(t)
    await session.flush()
    for i in range(n_contracts):
        session.add(Contract(tenant_id=t.id, code=f"C-{i}", type=ContractType.hour_bank,
                             starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                             initial_hours=100, created_by="seed"))
    await session.commit()
    return t


@pytest.mark.asyncio
async def test_auto_selects_single_contract(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session, n_contracts=1)

    async def fake_create(**kw):
        assert kw["contract_id"]  # auto-selected
        return znuny_ticket.TicketCreated(99, "N99")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        out = await TicketingService(s, znuny_ticket).open_ticket(
            OpenTicketInput(customer_user="joe", customer_id="ACME", title="t", body="b",
                            service=None, type_=None, priority=None, contract_id=None, attachments=[]),
        )
        assert out.znuny_ticket_id == 99


@pytest.mark.asyncio
async def test_requires_choice_when_multiple(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session, n_contracts=2)
    monkeypatch.setattr(znuny_ticket, "create_ticket",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("must not create")))
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ContractChoiceRequired):
            await TicketingService(s, znuny_ticket).open_ticket(
                OpenTicketInput(customer_user="joe", customer_id="ACME", title="t", body="b",
                                service=None, type_=None, priority=None, contract_id=None, attachments=[]),
            )


@pytest.mark.asyncio
async def test_unknown_contract_rejected(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session, n_contracts=2)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(NoActiveContract):
            await TicketingService(s, znuny_ticket).open_ticket(
                OpenTicketInput(customer_user="joe", customer_id="ACME", title="t", body="b",
                                service=None, type_=None, priority=None,
                                contract_id=str(uuid.uuid4()), attachments=[]),
            )
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd apps/sidecar && uv run pytest tests/test_ticketing_service.py -q`
Expected: FAIL — `ModuleNotFoundError: ...ticketing_service`.

- [ ] **Step 3: Implementar o serviço**

```python
# apps/sidecar/src/gerti_sidecar/domain/ticketing_service.py
"""Domínio de abertura de chamado (Spec #1E).

Regra de seleção de contrato (D-1E-2): 0 informado + 1 ativo => auto; 0 + >=2 =>
ContractChoiceRequired (422); informado e inexistente/ inativo sob RLS =>
NoActiveContract (404). Grava gerti.ticket_contract_link DEPOIS de o ticket
nascer no Znuny (billing-ready para a #1B).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import Contract, TicketContractLink
from gerti_sidecar.models.enums import ContractStatus


class NoActiveContract(Exception):
    """Contrato informado não existe / não está ativo sob o tenant (->404)."""


class ContractChoiceRequired(Exception):
    """Há >=2 contratos ativos e nenhum foi escolhido (->422)."""


@dataclass(frozen=True)
class OpenTicketInput:
    customer_user: str
    customer_id: str
    title: str
    body: str
    service: str | None
    type_: str | None
    priority: str | None
    contract_id: str | None
    attachments: list  # list[znuny_ticket.Attachment]


@dataclass(frozen=True)
class OpenedTicket:
    znuny_ticket_id: int
    ticket_number: str
    contract_id: str


class TicketingService:
    def __init__(self, session: AsyncSession, gi) -> None:
        self._session = session
        self._gi = gi

    async def _active_contract_ids(self) -> list[uuid.UUID]:
        # RLS já filtra por tenant (app.current_tenant via tenant_session_scope).
        rows = await self._session.execute(
            select(Contract.id).where(Contract.status == ContractStatus.active)
        )
        return [r[0] for r in rows.all()]

    async def _resolve_contract(self, requested: str | None) -> uuid.UUID:
        active = await self._active_contract_ids()
        if requested is not None:
            try:
                rid = uuid.UUID(requested)
            except ValueError as exc:
                raise NoActiveContract("contrato inválido") from exc
            if rid not in active:
                raise NoActiveContract("contrato não encontrado ou inativo")
            return rid
        if len(active) == 1:
            return active[0]
        if len(active) == 0:
            raise NoActiveContract("nenhum contrato ativo para abrir chamado")
        raise ContractChoiceRequired("selecione um contrato")

    async def open_ticket(self, data: OpenTicketInput) -> OpenedTicket:
        contract_id = await self._resolve_contract(data.contract_id)

        created = await self._gi.create_ticket(
            customer_user=data.customer_user,
            customer_id=data.customer_id,
            title=data.title,
            body=data.body,
            service=data.service,
            type_=data.type_,
            priority=data.priority,
            contract_id=str(contract_id),
            attachments=data.attachments or None,
        )

        # tenant_id vem do GUC app.current_tenant; a FK + RLS garantem o escopo.
        tenant_row = await self._session.execute(select(Contract.tenant_id).where(Contract.id == contract_id))
        tenant_id = tenant_row.scalar_one()
        self._session.add(
            TicketContractLink(
                znuny_ticket_id=created.znuny_ticket_id,
                contract_id=contract_id,
                tenant_id=tenant_id,
                linked_by_rule=f"portal:{data.customer_user}",
            )
        )
        await self._session.flush()
        return OpenedTicket(created.znuny_ticket_id, created.ticket_number, str(contract_id))
```

- [ ] **Step 4: Rodar e ver passar + gate**

Run: `cd apps/sidecar && uv run pytest tests/test_ticketing_service.py -q && uv run ruff check . && uv run mypy src`
Expected: 3 passed; gate limpo.

- [ ] **Step 5: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/domain/ticketing_service.py apps/sidecar/tests/test_ticketing_service.py
git commit -m "feat(#1E fase 2): ticketing_service (seleção de contrato + grava ticket_contract_link)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 9: Router `ticketing_meta.py` (contratos selecionáveis + form-meta, não-admin)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/routers/ticketing_meta.py`
- Modify: `apps/sidecar/src/gerti_sidecar/main.py:17-67` (registrar o router)
- Test: `apps/sidecar/tests/test_ticketing_meta_router.py`

- [ ] **Step 1: Escrever o teste** (qualquer papel logado vê; 401 sem sessão)

```python
# apps/sidecar/tests/test_ticketing_meta_router.py
from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Contract, Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_selectable_contracts_visible_to_helpdesk(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
                         webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
    session.add(inst)
    await session.flush()
    t = Tenant(legal_name="Acme", trade_name="Acme", document="1",
               znuny_customer_id="ACME", znuny_instance_id=inst.id, subdomain="acme")
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Acme"))
    session.add(Contract(tenant_id=t.id, code="C-1", type=ContractType.hour_bank,
                         starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                         initial_hours=100, created_by="seed"))
    await session.commit()
    monkeypatch.setattr(db, "AdminSessionLocal",
                        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/v1/ticketing/contracts", headers=h)).status_code == 401
        # papel helpdesk (NÃO admin) deve enxergar — diferente de /v1/contracts
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/ticketing/contracts", headers=h)
        assert r.status_code == 200
        rows = r.json()
        assert rows[0]["code"] == "C-1"
        assert "id" in rows[0]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd apps/sidecar && uv run pytest tests/test_ticketing_meta_router.py -q`
Expected: FAIL (404 do endpoint inexistente, assert quebra).

- [ ] **Step 3: Implementar o router**

```python
# apps/sidecar/src/gerti_sidecar/routers/ticketing_meta.py
"""Catálogo para o formulário de abertura (Spec #1E) — NÃO-admin.

/v1/ticketing/contracts: contratos ATIVOS selecionáveis (qualquer papel logado).
Diferente de /v1/contracts (#1F-b, require_admin): aqui devolve só o necessário
ao dropdown, sob RLS por tenant. /v1/ticketing/form-meta: serviços/prioridades/
tipos do Znuny via GI.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.contract_read_service import ContractReadService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable
from gerti_sidecar.models import Contract
from gerti_sidecar.models.enums import ContractStatus

router = APIRouter(prefix="/ticketing", tags=["ticketing"])


class SelectableContract(BaseModel):
    id: uuid.UUID
    code: str
    type: str
    saldo_label: str | None


@router.get("/contracts", response_model=list[SelectableContract])
async def selectable_contracts(
    _session: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[SelectableContract]:
    rows = await session.execute(
        select(Contract).where(Contract.status == ContractStatus.active).order_by(Contract.code)
    )
    reader = ContractReadService(session)
    out: list[SelectableContract] = []
    for contract in rows.scalars().all():
        bal = await reader.balance(contract.id)
        label = None if bal.remaining is None else f"{bal.kind} {bal.remaining:g}"
        out.append(
            SelectableContract(id=contract.id, code=contract.code, type=str(contract.type), saldo_label=label)
        )
    return out


class FormMeta(BaseModel):
    services: list[dict]
    priorities: list[dict]
    types: list[dict]


@router.get("/form-meta", response_model=FormMeta)
async def form_meta(
    session_payload: SessionPayload = Depends(get_current_session),
) -> FormMeta:
    try:
        meta = await znuny_ticket.form_meta(customer_user=session_payload["customer_login"])
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return FormMeta(services=meta["services"], priorities=meta["priorities"], types=meta["types"])
```

> **Nota de implementação:** confirme a assinatura de `ContractReadService(session).balance(contract_id)` no arquivo `apps/sidecar/src/gerti_sidecar/domain/contract_read_service.py` (já usada em `routers/contracts.py`). Se `balance` exigir o objeto `Contract` em vez do id, ajuste a chamada conforme o uso existente em `contracts.py`.

- [ ] **Step 4: Registrar o router no `main.py`** (após a linha 62, `contracts.router`)

No bloco de imports (linha 17-...), adicionar `ticketing_meta` à tupla `from gerti_sidecar.routers import (...)`. Depois, após `app.include_router(dashboard.router, ...)` (linha 63), inserir:
```python
    app.include_router(ticketing_meta.router, prefix=settings.api_v1_prefix)
```

- [ ] **Step 5: Rodar e ver passar + gate**

Run: `cd apps/sidecar && uv run pytest tests/test_ticketing_meta_router.py -q && uv run ruff check . && uv run mypy src`
Expected: 1 passed; gate limpo.

- [ ] **Step 6: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/routers/ticketing_meta.py apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/tests/test_ticketing_meta_router.py
git commit -m "feat(#1E fase 2): GET /v1/ticketing/{contracts,form-meta} (não-admin, RLS)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 10: Router `tickets.py` (criar/listar/detalhe/responder + anexos + posse + papel)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/routers/tickets.py`
- Modify: `apps/sidecar/src/gerti_sidecar/main.py` (registrar)
- Test: `apps/sidecar/tests/test_tickets_router.py`

- [ ] **Step 1: Escrever os testes** (criar via multipart; escopo por papel; posse; erros GI)

```python
# apps/sidecar/tests/test_tickets_router.py
from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Contract, Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.models.enums import ContractType


async def _seed(session):
    inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
                         webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
    session.add(inst); await session.flush()
    t = Tenant(legal_name="Acme", trade_name="Acme", document="1",
               znuny_customer_id="ACME", znuny_instance_id=inst.id, subdomain="acme")
    session.add(t); await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Acme"))
    contract = Contract(tenant_id=t.id, code="C-1", type=ContractType.hour_bank,
                        starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                        initial_hours=100, created_by="seed")
    session.add(contract); await session.commit()
    return t


@pytest.mark.asyncio
async def test_open_ticket_single_contract(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test"); get_settings.cache_clear()
    t = await _seed(session)

    async def fake_create(**kw):
        return znuny_ticket.TicketCreated(123, "2026010100001")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    monkeypatch.setattr(db, "AdminSessionLocal",
                        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app(); st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/tickets", headers=h,
                         data={"title": "t", "body": "b"})  # sem contract_id -> auto
        assert r.status_code == 201
        assert r.json()["ticket_number"] == "2026010100001"


@pytest.mark.asyncio
async def test_get_ticket_ownership(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test"); get_settings.cache_clear()
    t = await _seed(session)

    async def fake_get(*, znuny_ticket_id, customer_id):
        # cliente da empresa ACME tentando ler ticket de outra => GI levanta WriteError
        from gerti_sidecar.integrations.znuny_ticket import ZnunyWriteError
        raise ZnunyWriteError("ticket not found")

    monkeypatch.setattr(znuny_ticket, "get_ticket", fake_get)
    monkeypatch.setattr(db, "AdminSessionLocal",
                        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app(); st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/tickets/999", headers=h)
        assert r.status_code == 404
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd apps/sidecar && uv run pytest tests/test_tickets_router.py -q`
Expected: FAIL (router inexistente).

- [ ] **Step 3: Implementar o router**

```python
# apps/sidecar/src/gerti_sidecar/routers/tickets.py
"""Tickets do portal (Spec #1E): criar / listar / detalhe / responder.

Auth = get_current_session (qualquer papel logado). Escopo de listagem por papel
(#1H): helpdesk => 'own'; admin => 'company'. Guarda de posse anti-IDOR no
detalhe/reply (o GI valida CustomerID; ZnunyWriteError 'not found' => 404).
Anexos via multipart no POST. RLS por tenant para gravar o link.
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.ticketing_service import (
    ContractChoiceRequired,
    NoActiveContract,
    OpenTicketInput,
    TicketingService,
)
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.models import Tenant
from gerti_sidecar.models.enums import PortalRole

router = APIRouter(prefix="/tickets", tags=["tickets"])

_MAX_ATTACH_BYTES = 10 * 1024 * 1024  # 10 MB por arquivo
_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".txt", ".log", ".csv", ".zip", ".doc", ".docx"}


class OpenedTicketOut(BaseModel):
    znuny_ticket_id: int
    ticket_number: str
    contract_id: str


def _customer_id(request: Request) -> str:
    tenant: Tenant = request.state.tenant
    return tenant.znuny_customer_id


@router.post("", status_code=201, response_model=OpenedTicketOut)
async def open_ticket(
    request: Request,
    title: str = Form(...),
    body: str = Form(...),
    contract_id: str | None = Form(None),
    service: str | None = Form(None),
    type_: str | None = Form(None, alias="type"),
    priority: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> OpenedTicketOut:
    attachments = []
    for f in files:
        raw = await f.read()
        if len(raw) > _MAX_ATTACH_BYTES:
            raise HTTPException(status_code=413, detail="attachment_too_large")
        name = f.filename or "anexo"
        ext = name[name.rfind(".") :].lower() if "." in name else ""
        if ext not in _ALLOWED_EXT:
            raise HTTPException(status_code=415, detail=f"ext_not_allowed:{ext}")
        attachments.append(
            znuny_ticket.Attachment(
                filename=name,
                content_type=f.content_type or "application/octet-stream",
                content_base64=base64.b64encode(raw).decode("ascii"),
            )
        )

    data = OpenTicketInput(
        customer_user=session_payload["customer_login"],
        customer_id=_customer_id(request),
        title=title,
        body=body,
        service=service,
        type_=type_,
        priority=priority,
        contract_id=contract_id,
        attachments=attachments,
    )
    try:
        out = await TicketingService(session, znuny_ticket).open_ticket(data)
    except ContractChoiceRequired as exc:
        raise HTTPException(status_code=422, detail="contract_required") from exc
    except NoActiveContract as exc:
        raise HTTPException(status_code=404, detail="contract_not_found") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return OpenedTicketOut(
        znuny_ticket_id=out.znuny_ticket_id, ticket_number=out.ticket_number, contract_id=out.contract_id
    )


@router.get("")
async def list_tickets(
    request: Request,
    session_payload: SessionPayload = Depends(get_current_session),
) -> list[dict]:
    scope = "company" if session_payload["role"] == PortalRole.admin.value else "own"
    try:
        rows = await znuny_ticket.search_tickets(
            scope=scope,
            customer_user=session_payload["customer_login"],
            customer_id=_customer_id(request),
        )
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return [
        {
            "znuny_ticket_id": r.znuny_ticket_id,
            "ticket_number": r.ticket_number,
            "title": r.title,
            "state": r.state,
            "created": r.created,
            "contract_id": r.contract_id,
        }
        for r in rows
    ]


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    request: Request,
    session_payload: SessionPayload = Depends(get_current_session),
) -> dict:
    try:
        d = await znuny_ticket.get_ticket(znuny_ticket_id=ticket_id, customer_id=_customer_id(request))
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return {
        "znuny_ticket_id": d.znuny_ticket_id,
        "ticket_number": d.ticket_number,
        "title": d.title,
        "state": d.state,
        "priority": d.priority,
        "created": d.created,
        "contract_id": d.contract_id,
        "articles": d.articles,
    }


class ReplyBody(BaseModel):
    body: str


@router.post("/{ticket_id}/reply", status_code=201)
async def reply_ticket(
    ticket_id: int,
    payload: ReplyBody,
    request: Request,
    session_payload: SessionPayload = Depends(get_current_session),
) -> dict:
    try:
        await znuny_ticket.reply_ticket(
            znuny_ticket_id=ticket_id,
            customer_user=session_payload["customer_login"],
            customer_id=_customer_id(request),
            body=payload.body,
        )
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="ticket_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return {"ok": True}
```

> **Dependência de pacote:** o `UploadFile`/`Form` exige `python-multipart`. Confirme que está nas deps do sidecar (`pyproject.toml`); se ausente, `uv add python-multipart` e commitar o lockfile junto.

- [ ] **Step 4: Registrar o router no `main.py`** (importar `tickets` e adicionar após `ticketing_meta`):
```python
    app.include_router(tickets.router, prefix=settings.api_v1_prefix)
```

- [ ] **Step 5: Rodar e ver passar + gate completo**

Run: `cd apps/sidecar && uv run pytest tests/test_tickets_router.py tests/test_ticketing_service.py tests/test_ticketing_meta_router.py tests/test_znuny_ticket_client.py -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: todos passam; gate limpo.

- [ ] **Step 6: Commit**

```bash
git add apps/sidecar/src/gerti_sidecar/routers/tickets.py apps/sidecar/src/gerti_sidecar/main.py apps/sidecar/tests/test_tickets_router.py apps/sidecar/pyproject.toml apps/sidecar/uv.lock
git commit -m "feat(#1E fase 2): router /v1/tickets (criar/listar/detalhe/responder, anexos, posse, papel)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 11: Grep-guard — endpoints de ticket não escrevem no schema znuny

**Files:**
- Test: `apps/sidecar/tests/test_ticketing_no_direct_znuny.py`

- [ ] **Step 1: Escrever o guard** (espelha `test_portal_read_only_guard.py`)

```python
# apps/sidecar/tests/test_ticketing_no_direct_znuny.py
"""Spec #0: escrita/leitura de ticket SÓ via GI. Nenhum SQL direto no schema
znuny/public a partir dos módulos de ticketing."""

from __future__ import annotations

import pathlib

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "gerti_sidecar"
_FILES = [
    _SRC / "routers" / "tickets.py",
    _SRC / "routers" / "ticketing_meta.py",
    _SRC / "domain" / "ticketing_service.py",
]
_FORBIDDEN = ('"public.', "'public.", '"znuny.', "'znuny.", "customer_user", "customer_company")


def test_no_direct_znuny_schema_access():
    for f in _FILES:
        text = f.read_text(encoding="utf-8").lower()
        for needle in _FORBIDDEN:
            assert needle.lower() not in text, f"{f.name} referencia schema znuny diretamente: {needle}"
```

- [ ] **Step 2: Rodar e ver passar**

Run: `cd apps/sidecar && uv run pytest tests/test_ticketing_no_direct_znuny.py -q`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add apps/sidecar/tests/test_ticketing_no_direct_znuny.py
git commit -m "test(#1E fase 2): grep-guard — ticketing só fala com Znuny via GI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 3 — Portal: telas (conduzidas pelo especialista frontend/UX, D-1E-9)

> **REQUIRED SUB-SKILL para esta fase:** invocar a skill `frontend-design` antes de escrever as telas. Aceite (D-1E-9): o cliente final entende de bate-pronto — linguagem clara em PT-BR, estados vazio/carregando/erro compreensíveis, feedback explícito de cada ação (toast de sucesso, mensagens de erro acionáveis), acessibilidade (labels, foco, contraste). Reusar Nuxt UI (`UForm/UInput/USelect/UTextarea/UButton/UAlert/UCard/UBadge`), tokens de marca (`--brand-primary`), nunca cor de marca em `warning`/`error` (H8). Padrões de proxy/SSR/cookie já existentes (ver `apps/portal/server/utils/sidecar.ts`, `server/api/portal/*`, `pages/login.vue`, `middleware/auth.ts`, `layouts/default.vue`).

### Task 12: Server proxies do portal (passthrough para o sidecar)

**Files:**
- Create: `apps/portal/server/api/portal/ticketing/contracts.get.ts`
- Create: `apps/portal/server/api/portal/ticketing/form-meta.get.ts`
- Create: `apps/portal/server/api/portal/tickets/index.get.ts`
- Create: `apps/portal/server/api/portal/tickets/index.post.ts`
- Create: `apps/portal/server/api/portal/tickets/[id].get.ts`
- Create: `apps/portal/server/api/portal/tickets/[id]/reply.post.ts`

- [ ] **Step 1: Criar os 4 proxies GET/JSON simples** (padrão de `server/api/portal/dashboard.get.ts`)

`contracts.get.ts`:
```ts
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/ticketing/contracts')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
```
`form-meta.get.ts`:
```ts
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/ticketing/form-meta')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
```
`tickets/index.get.ts`:
```ts
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/tickets')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
```
`tickets/[id].get.ts`:
```ts
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/tickets/${id}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
```
`tickets/[id]/reply.post.ts`:
```ts
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, `/v1/tickets/${id}/reply`, {
    method: 'POST', body,
  })
  setResponseStatus(event, status)
  return data
})
```

- [ ] **Step 2: Criar o proxy multipart `tickets/index.post.ts`**

> O `index.post` precisa repassar `multipart/form-data` (anexos) sem reserializar. Estratégia: ler o corpo bruto e o content-type e repassar via `sidecarFetch` com passthrough. Se `sidecarFetch` (ver `server/utils/sidecar.ts`) não suportar corpo bruto, estender o helper para aceitar `rawBody`/`contentType`. Implementação:

```ts
export default defineEventHandler(async (event) => {
  // multipart: lê os bytes crus e o content-type original (com boundary)
  const contentType = getRequestHeader(event, 'content-type') || ''
  const raw = await readRawBody(event, false) as Buffer // Buffer
  const { status, data } = await sidecarFetch(event, '/v1/tickets', {
    method: 'POST',
    body: raw,
    headers: { 'content-type': contentType },
  })
  setResponseStatus(event, status)
  return data
})
```

> **Confirme** no `server/utils/sidecar.ts` que `sidecarFetch` aceita `method`/`body`/`headers` e encaminha o cookie `gsid`. Se hoje ele só faz GET, estenda-o (mantendo o forward de cookie e `x-forwarded-host`) — é a mesma mudança que os proxies de auth (`server/api/auth/login.post.ts`) já exercem para POST JSON; o delta aqui é aceitar `body: Buffer` + `content-type` custom para multipart.

- [ ] **Step 3: Verificação de tipo do portal**

Run: `cd apps/portal && npx nuxi typecheck` (ou o script de typecheck do projeto — ver `package.json`)
Expected: sem erros de tipo nos arquivos novos.

- [ ] **Step 4: Commit**

```bash
git add apps/portal/server/api/portal/ticketing apps/portal/server/api/portal/tickets apps/portal/server/utils/sidecar.ts
git commit -m "feat(#1E fase 3): server proxies de ticketing no portal (GET + POST multipart)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 13: Página `/tickets/novo` — formulário de abertura (form A, página única)

**Files:**
- Create: `apps/portal/pages/tickets/novo.vue`

- [ ] **Step 1: Invocar a skill `frontend-design`** e construir a tela conforme o mockup aprovado (`.superpowers/brainstorm/.../form-layout.html`, opção A).

Requisitos funcionais (contrato com o backend, fixos):
- `definePageMeta({ middleware: 'auth' })`, layout `default`.
- Ao montar (SSR): `GET /api/portal/ticketing/contracts` e `GET /api/portal/ticketing/form-meta`.
- **Seletor de contrato condicional (D-1E-2):** se `contracts.length <= 1`, NÃO renderiza o select (auto-vincula no backend); se `>= 2`, renderiza `USelect` obrigatório (`code` + `saldo_label`).
- Campos: serviço (`USelect`, opcional), tipo (`USelect`, opcional), prioridade (`USelect`, default "normal"), assunto (`UInput`, obrigatório), descrição (`UTextarea`, obrigatório), anexos (`UInput type=file` múltiplo).
- Submit: monta `FormData` (campos + `files[]`) e `POST /api/portal/tickets` (multipart). Em 201 → `navigateTo('/tickets/' + resp.znuny_ticket_id)` com toast de sucesso (`useToast`). Em 422 (`contract_required`) → realça o select com mensagem clara. Em 4xx/5xx → `UAlert` com mensagem em PT-BR acionável.
- UX (D-1E-9): botão com estado `:loading`; desabilitar durante o envio; mensagens em PT-BR; `warning`/`error` nunca usam cor de marca.

- [ ] **Step 2: Verificação manual no portal de dev**

Run: subir o portal de dev (`cd apps/portal && npm run dev`) apontando `SIDECAR_URL` ao sidecar local; abrir `/tickets/novo` autenticado num tenant com 1 contrato (sem select) e com 2 (com select). Conferir que o submit cria e redireciona.
Expected: criação OK; seletor condicional correto.

- [ ] **Step 3: Commit**

```bash
git add apps/portal/pages/tickets/novo.vue
git commit -m "feat(#1E fase 3): página /tickets/novo (form A, seletor de contrato condicional)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 14: Página `/tickets` — lista (substitui o placeholder)

**Files:**
- Modify: `apps/portal/pages/tickets.vue` (hoje placeholder #1H) → lista real

- [ ] **Step 1: Construir a lista** (skill `frontend-design`)

Requisitos:
- `GET /api/portal/tickets` (SSR via `useAsyncData`). O backend já escopa por papel.
- Render: tabela/cards com número, assunto, badge de estado, contrato (código quando resolvível — opcional: mapear `contract_id`→`code` via os contratos selecionáveis, ou só exibir "vinculado"), data. Linha clicável → `/tickets/[id]`.
- Botão primário "Novo chamado" → `/tickets/novo`.
- **Estado vazio claro** (D-1E-9): ilustração/í­cone + "Você ainda não abriu chamados" + CTA. Estado de carregando e de erro (sidecar 503) com mensagem em PT-BR.

- [ ] **Step 2: Verificação manual**

Run: abrir `/tickets` autenticado; conferir lista, estado vazio, e clique navegando ao detalhe.
Expected: lista correta por papel; vazio e erro tratados.

- [ ] **Step 3: Commit**

```bash
git add apps/portal/pages/tickets.vue
git commit -m "feat(#1E fase 3): página /tickets — lista de chamados por papel (substitui placeholder)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 15: Página `/tickets/[id]` — detalhe + responder

**Files:**
- Create: `apps/portal/pages/tickets/[id].vue`

- [ ] **Step 1: Construir o detalhe** (skill `frontend-design`)

Requisitos:
- `GET /api/portal/tickets/[id]` (SSR). 404 → página "chamado não encontrado" amigável (não vaza existência).
- Cabeçalho: assunto, badge de estado, prioridade, contrato vinculado, data.
- Thread de artigos (`articles[]`): autor (`From`/`SenderType`), data, corpo. Diferenciar visualmente cliente vs. agente (sem cor de marca em estados semânticos).
- Caixa de resposta: `UTextarea` + botão "Responder" → `POST /api/portal/tickets/[id]/reply` → re-fetch da thread + toast. Estados de loading/erro.
- UX (D-1E-9): ordem cronológica clara, foco na caixa de resposta, mensagens em PT-BR.

- [ ] **Step 2: Verificação manual (fluxo completo)**

Run: abrir um chamado criado na Task 13, conferir a thread, responder e ver a resposta aparecer.
Expected: detalhe + resposta funcionam; 404 amigável para id inexistente.

- [ ] **Step 3: Adicionar "Chamados" à navegação do header**

**Files:** Modify `apps/portal/layouts/default.vue` (nav por papel) — incluir link "Chamados" → `/tickets` para os papéis que devem vê-lo (helpdesk e admin). Seguir o padrão de nav-por-papel já existente no layout.

- [ ] **Step 4: Commit**

```bash
git add apps/portal/pages/tickets/[id].vue apps/portal/layouts/default.vue
git commit -m "feat(#1E fase 3): página /tickets/[id] (detalhe + responder) + nav 'Chamados'

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 16: e2e smoke do portal (abrir→listar→detalhe→responder, sidecar mockado)

**Files:**
- Create/Modify: teste e2e do portal seguindo o padrão de `apps/sidecar/tests/test_portal_e2e_smoke.py` **ou** o harness de teste do portal (`apps/portal`), conforme onde os e2e do portal vivem hoje.

- [ ] **Step 1: Localizar o harness e2e do portal**

Run: `ls apps/portal/test* apps/portal/tests 2>/dev/null; grep -rl "portal_e2e\|playwright\|vitest" apps/portal 2>/dev/null | head`
Expected: identifica onde os testes de portal rodam (vitest/playwright). Seguir esse padrão.

- [ ] **Step 2: Escrever o smoke**

Cobrir: (a) `/tickets/novo` com 1 contrato não mostra o select e cria; (b) com 2 contratos mostra o select e exige escolha; (c) `/tickets` lista; (d) `/tickets/[id]` mostra thread e o reply chama o endpoint. Mockar as respostas do sidecar (`/v1/ticketing/*`, `/v1/tickets*`).

- [ ] **Step 3: Rodar**

Run: o comando de teste do portal (ex.: `cd apps/portal && npm test`)
Expected: smoke verde.

- [ ] **Step 4: Commit**

```bash
git add apps/portal/<arquivos-de-teste>
git commit -m "test(#1E fase 3): e2e smoke do portal (abrir/listar/detalhe/responder)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 4 — Deploy + documentação (padrão voyager, mesmo PR)

### Task 17: Runbook de deploy em `OPS.md`

**Files:**
- Modify: `.ia/OPS.md` (nova seção "Deploy do fluxo de tickets do portal (Spec #1E)")

- [ ] **Step 1: Escrever o runbook** (espelha a seção #1G-a), cobrindo:
  - Pré-req: `ZNUNY_TICKET_WS_URL` em `.env.prod` (base do GertiTicket, p.ex.
    `https://znuny-dev.was.dev.br/znuny/nph-genericinterface.pl/Webservice/GertiTicket`); `ZNUNY_WS_TOKEN` já presente.
  - `git pull` da branch; `DC="docker compose --env-file .env --env-file .env.prod --profile gerti"`.
  - Rebuild `znuny-web` + recria `znuny-web`/`znuny-daemon` (downtime curto).
  - `perl scripts/ensure-gerti-dynamicfield.pl` (idempotente) + import idempotente do `GertiTicket.yml` (guard: `Admin::WebService::List` deve listar `GertiCustomerAuth`+`GertiAdmin`+`GertiTicket`).
  - Rebuild `sidecar` (sem migration) + rebuild `portal`.
  - Verificação e2e em prod (abrir chamado real vinculado a contrato; conferir DynamicField + linha em `ticket_contract_link`; limpar throwaway).
  - Serviços anteriores intactos (`znuny`/`api-dev`/`aurora`/`technova`/landing curls).
  - Rollback: `$DC stop portal sidecar`; reverter sha de `znuny/` + rebuild; **NUNCA** `make reset`.

- [ ] **Step 2: Commit**

```bash
git add .ia/OPS.md
git commit -m "docs(#1E): runbook de deploy do fluxo de tickets do portal

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 18: Atualizar `ARCHITECTURE.md` + `INTEGRATION.md`

**Files:**
- Modify: `.ia/ARCHITECTURE.md` (subseção no bloco do Portal: fluxo de tickets + GertiTicket + DynamicField)
- Modify: `.ia/INTEGRATION.md` (tabela (e): linhas de #1E como **Pronto**; registrar o webservice `GertiTicket` e o DynamicField `GertiContractId`; nota de que #1B/cobrança é o próximo)

- [ ] **Step 1: Editar os dois arquivos** com o estado real pós-implementação (sem inventar "deployado" antes de a Fase 4 rodar em prod — marcar "Pronto, gateado; deploy per runbook").

- [ ] **Step 2: Commit**

```bash
git add .ia/ARCHITECTURE.md .ia/INTEGRATION.md
git commit -m "docs(#1E): ARCHITECTURE + INTEGRATION — fluxo de tickets do portal (GertiTicket, DynamicField)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 19: Gate final consolidado

- [ ] **Step 1: Sidecar — gate completo**

Run: `cd apps/sidecar && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`
Expected: tudo verde (inclui os testes novos das Tasks 7-11).

- [ ] **Step 2: Stack Znuny base intocada**

Run: `make test`
Expected: 24/24 asserts verdes — o `gerti` não quebrou o núcleo.

- [ ] **Step 3: Portal — typecheck + testes**

Run: `cd apps/portal && npx nuxi typecheck && npm test`
Expected: sem erros de tipo; smoke verde.

- [ ] **Step 4: Verificação final + commit (se houver ajustes)**

Confirmar que todos os asserts dos critérios da spec §5 estão cobertos por teste verde. Se algo ficou descoberto, voltar à task correspondente. Commit de quaisquer ajustes finais com `fix(#1E): ...`.

---

## Self-Review (cobertura da spec)

- **D-1E-1 escopo completo** → Tasks 13 (novo), 14 (lista), 15 (detalhe/responder). ✅
- **D-1E-2 seleção de contrato (auto/≥2/422)** → Task 8 (`_resolve_contract`) + 10 (mapeia 422/404) + 13 (UI condicional). ✅
- **D-1E-3 campos (serviço/tipo/prioridade/anexos)** → Task 10 (multipart + Form) + 13 (form). ✅
- **D-1E-4 DynamicField + tabela** → Task 1 (ValueSet GertiContractId) + 5 (ensure-dynamicfield) + 8 (grava o link). ✅
- **D-1E-5 visibilidade por papel** → Task 10 (`scope` por `role`) + 2 (TicketSearch own/company). ✅
- **D-1E-6 mecanismo GertiTicket (AccessToken)** → Tasks 1-4. ✅
- **D-1E-7 layout página única** → Task 13. ✅
- **D-1E-8 cobrança próxima spec** → fora de escopo; link billing-ready em Task 8. ✅
- **D-1E-9 UX-first** → Fase 3 inteira sob skill `frontend-design`; aceite explícito nas Tasks 13-15. ✅
- **Segurança §3:** endpoint selecionável não-admin (Task 9), escopo por papel (Task 10), posse anti-IDOR (Tasks 2/10), anexos validados (Task 10), grep-guard só-GI (Task 11). ✅
- **Dados §4:** tabela já migrada (0008) — sem migration nova; Task 8 grava nela. ✅
- **Testes §5:** Tasks 7-11 (sidecar), 6 (Znuny smoke), 16 (portal e2e), 19 (gate + `make test`). ✅
- **Deploy §6:** Tasks 17-18 (runbook + docs), 6 (comandos reusados). ✅

**Pontos a confirmar durante a execução (sinalizados inline, não placeholders):** assinatura exata de `ContractReadService.balance` (Task 9), capacidade do `sidecarFetch` para POST/multipart (Task 12), presença de `python-multipart` (Task 10), localização do harness e2e do portal (Task 16), e os nomes nativos exatos da API de Article do Znuny 7.2 — todos verificáveis no smoke vivo da Fase 1 (Task 6) e nos `perl -c` (Tasks 1-3).
```
