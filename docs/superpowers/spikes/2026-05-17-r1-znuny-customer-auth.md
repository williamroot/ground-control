# SPIKE R1 (#1F-a) — Mecanismo de validação de credencial de customer Znuny

**Data:** 2026-05-18 (plano datado 2026-05-17)
**Objetivo:** Decidir, por investigação concreta contra o Znuny prod vivo via
`ssh gc`, COMO o sidecar valida uma credencial de *customer* Znuny SEM
GertiHooks/#1B, e congelar o contrato `authenticate_customer` (ADR D14).
**Acesso usado:** exclusivamente `ssh gc '<cmd>'` (jump alias via node
`postgres` — caminho Tailscale direto quebrado, ver `.ia/OPS.md`).
**Tolerância zero:** todas as saídas abaixo são reais e observadas. Nada fabricado.

---

## Step 1 — Inventário de webservices Znuny existentes (read-only)

Comando:

```
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List"'
```

Saída real:

```
Listing all web services...
Done.
```

**Interpretação:** NENHUM webservice cadastrado no Znuny prod. Não há nada
para `Admin::WebService::Dump <ID>` (lista vazia). O webservice
`Session::SessionCreate` precisará ser criado/importado como etapa de
deploy posterior (Task 5/6) — o spike apenas prova o mecanismo e congela
o contrato.

---

## Step 2 — Probe da operação core GI Session

Comando:

```
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c "ls /opt/otrs/Kernel/GenericInterface/Operation/Session/"'
```

Saída real:

```
Common.pm
SessionCreate.pm
SessionGet.pm
SessionRemove.pm
```

**Interpretação:** `SessionCreate.pm` PRESENTE (código core Znuny, não
GertiHooks/#1B). Critério PRIMARY do Step 3 se aplica.

---

## Step 2b — Fonte de `SessionCreate.pm` (campo de login exato)

Comando:

```
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c "cat /opt/otrs/Kernel/GenericInterface/Operation/Session/SessionCreate.pm"'
```

Trechos reais relevantes (POD da `Run()` e corpo):

```
    my $Result = $OperationObject->Run(
        Data => {
            UserLogin         => 'Agent1',          # optional, provide UserLogin or CustomerUserLogin
            # or
            CustomerUserLogin => 'Customer1',       # optional, provide UserLogin or CustomerUserLogin

            Password          => 'some password',   # plain text password
        },
    );

    $Result = {
        Success      => 1,                          # 0 or 1
        ErrorMessage => '',                         # In case of an error
        Data         => {
            SessionID => $SessionID,
        },
    };
```

```
    for my $Needed (qw( Password )) {
        if ( !$Param{Data}->{$Needed} ) {
            return $Self->ReturnError(
                ErrorCode    => 'SessionCreate.MissingParameter',
                ErrorMessage => "SessionCreate: $Needed parameter is missing!",
            );
        }
    }

    my $SessionID = $Self->CreateSessionID( %Param );

    if ( !$SessionID ) {
        return $Self->ReturnError(
            ErrorCode    => 'SessionCreate.AuthFail',
            ErrorMessage => "SessionCreate: Authorization failing!",
        );
    }

    return {
        Success => 1,
        Data    => { SessionID => $SessionID },
    };
```

**Campo de login de customer confirmado: `CustomerUserLogin`** (+ `Password`,
texto plano). Sucesso → `Data.SessionID`. Credencial inválida →
`SessionCreate.AuthFail`.

---

## Step 2c — `Session::Common::CreateSessionID` (prova de auth de CUSTOMER)

Comando:

```
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c "sed -n \"1,200p\" /opt/otrs/Kernel/GenericInterface/Operation/Session/Common.pm"'
```

Trecho real decisivo:

```
    elsif ( defined $Param{Data}->{CustomerUserLogin} && $Param{Data}->{CustomerUserLogin} ) {

        # if UserCustomerLogin
        my $PostUser = $Param{Data}->{CustomerUserLogin} || '';

        # check submitted data
        $User = $Kernel::OM->Get('Kernel::System::CustomerAuth')->Auth(
            User           => $PostUser,
            Pw             => $PostPw,
            TwoFactorToken => $PostTwoFactorToken,
        );
        ...
        $UserType = 'Customer';
    }

    # login is invalid
    return if !$User;
```

**Interpretação:** com `CustomerUserLogin` o módulo chama
`Kernel::System::CustomerAuth->Auth` (autenticação de CUSTOMER, respeita
`Customer::AuthModule` do Znuny — não agente). `$User` falso → retorna
undef → `SessionCreate.pm` devolve `SessionCreate.AuthFail`. Isso valida
exatamente a credencial de customer sem GertiHooks/#1B.

---

## Step 3 — Critério aplicado

`SessionCreate.pm` presente ⇒ **PRIMARY**. FALLBACK (query read-only +
CryptType) NÃO foi necessário e NÃO foi exercido.

---

## Endpoint / token — linha única `gerti.znuny_instance`

Comando:

```
ssh gc 'cd ~/ground-control && docker compose exec -T postgres psql -U znuny -d znuny -c "\d gerti.znuny_instance" -c "SELECT * FROM gerti.znuny_instance;"'
```

Saída real (linha de dados):

```
                  id                  |          name          |           base_url           |     db_dsn_secret_ref      |    webservice_token_secret_ref     |   webhook_signing_secret_ref    | mode | status |         created_at
--------------------------------------+------------------------+------------------------------+----------------------------+------------------------------------+---------------------------------+------+--------+-----------------------------
 b437f4d5-8266-4270-9253-ef536c8ff59c | Gerti Prod (znuny-dev) | https://znuny-dev.was.dev.br | vault://gerti/znuny-dev/db | vault://gerti/znuny-dev/webservice | vault://gerti/znuny-dev/webhook | pool | active | 2026-05-17 16:29:10.9778+00
(1 row)
```

Colunas relevantes ao contrato:
- `base_url` = `https://znuny-dev.was.dev.br`
- `webservice_token_secret_ref` = `vault://gerti/znuny-dev/webservice`
- `db_dsn_secret_ref` = `vault://gerti/znuny-dev/db` (só relevante se FALLBACK; NÃO é o caso)

---

## Decisão (resumo) → ver `.ia/DECISIONS.md` D14

PRIMARY: webservice GI REST provider expondo `Session::SessionCreate`,
rota `POST /Session`, campo de login `CustomerUserLogin` + `Password`.
Contrato congelado:

```python
class ZnunyUnavailable(RuntimeError): ...

async def authenticate_customer(login: str, password: str) -> bool: ...
```

- corpo com `SessionID` (HTTP 2xx) → `return True`
- `Error`/`SessionCreate.AuthFail`/HTTP 4xx → `return False`
- erro de conexão / timeout / HTTP 5xx → `raise ZnunyUnavailable`

## Definição EXATA do webservice a importar (etapa de deploy — Task 5/6)

Provider webservice (YAML SysConfig / `Admin::WebService` import), p.ex.:

```yaml
Description: Gerti sidecar customer auth
FrameworkVersion: 7.2.x
Provider:
  Transport:
    Type: HTTP::REST
    Config:
      KeepAlive: ''
      MaxLength: 100000000
      RouteOperationMapping:
        SessionCreate:
          RequestMethod: [POST]
          Route: /Session
  Operation:
    SessionCreate:
      Type: Session::SessionCreate
      Description: Create a session id for a customer user
Debugger:
  DebugThreshold: error
  TestMode: 0
RemoteSystem: ''
```

Chamada esperada pelo sidecar:
`POST {base_url}/nph-genericinterface.pl/Webservice/<Name>/Session`
body JSON `{"CustomerUserLogin": login, "Password": password}`.
Token de acesso guardado em `webservice_token_secret_ref`
(`vault://gerti/znuny-dev/webservice`) — incluído conforme o esquema de
auth do webservice no momento da criação (Task 5/6).
