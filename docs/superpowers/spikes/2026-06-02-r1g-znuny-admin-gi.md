# SPIKE R1G (#1G-a) — Auth de AGENTE via GI + escrita de cliente (CustomerCompany/User) via GI

**Data:** 2026-06-02
**Objetivo:** Decidir, por investigação concreta contra o Znuny prod vivo via
`ssh gc`, os DOIS mecanismos de que o Console de Administração precisa, e
congelar os contratos para a execução paralela da Fase 1:
1. **Auth de agente Znuny via Generic Interface** (`Session::SessionCreate`
   com `UserLogin`+`Password` → `SessionID`).
2. **Escrita de cliente via GI** (criar `CustomerCompany` + `CustomerUser` +
   setar senha) — Spec #0: escrita no Znuny SEMPRE via GI, nunca SQL direto.
**Acesso usado:** exclusivamente `ssh gc '<cmd>'` (jump alias via node
`postgres` — path Tailscale direto quebrado, ver `.ia/OPS.md`).
**Tolerância zero:** todas as saídas abaixo são reais e observadas. Nada fabricado.

---

## Estado do alvo

```
ssh gc 'cd ~/ground-control && docker compose ps --format "{{.Service}}\t{{.Status}}"'
```

```
postgres        Up 2 weeks (healthy)
znuny-daemon    Up 2 weeks (healthy)
znuny-web       Up 2 weeks (healthy)
```

Znuny 7.2.3 vivo (mesma instância do spike R1/#1F, D14).

---

## INCÓGNITA 1 — Auth de AGENTE via GI

### Step 1.1 — namespaces de Operation embarcados

```
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c "ls /opt/otrs/Kernel/GenericInterface/Operation/"'
```

Saída real:

```
Common.pm
Session
Test
Ticket
User
```

`Session/` presente (mesma operação core do D14). `SessionCreate.pm` já
inventariado no spike R1 (#1F): aceita `UserLogin` **ou** `CustomerUserLogin`
+ `Password`.

### Step 1.2 — branch `UserLogin` (agente) em `Session/Common.pm`

```
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c "grep -n -A12 UserLogin /opt/otrs/Kernel/GenericInterface/Operation/Session/Common.pm"'
```

Trecho real decisivo (linhas 55-70):

```perl
    if ( defined $Param{Data}->{UserLogin} && $Param{Data}->{UserLogin} ) {

        # if UserLogin
        my $PostUser = $Param{Data}->{UserLogin} || '';

        # check submitted data
        $User = $Kernel::OM->Get('Kernel::System::Auth')->Auth(
            User           => $PostUser,
            Pw             => $PostPw,
            TwoFactorToken => $PostTwoFactorToken,
        );
        ...
        $UserType = 'User';
    }
    elsif ( defined $Param{Data}->{CustomerUserLogin} ... ) {
        ... $Kernel::OM->Get('Kernel::System::CustomerAuth')->Auth( ... )
```

**Interpretação:** com `UserLogin`, `SessionCreate` roteia para
`Kernel::System::Auth->Auth` (auth de AGENTE, respeita `AuthModule` do Znuny —
não customer). `$User` falso → `SessionCreate.AuthFail`. É o espelho exato do
caminho de customer do D14, trocando o campo de login.

### Step 1.3 — prova VIVA do agent-auth (válido + inválido)

Roda o MESMO `Kernel::System::Auth->Auth` que o `UserLogin` branch chama,
com um agente real seedado (`william`, admin — ver `.ia/DEMO.md`):

```
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c "
cd /opt/otrs && perl -I/opt/otrs -I/opt/otrs/Kernel/cpan-lib -I/opt/otrs/Custom -MKernel::System::ObjectManager -e '\''
local \$Kernel::OM = Kernel::System::ObjectManager->new();
my \$auth = \$Kernel::OM->Get(\"Kernel::System::Auth\");
my \$ok  = \$auth->Auth(User => \"william\", Pw => \"Gerti\@Demo2026\");
my \$bad = \$auth->Auth(User => \"william\", Pw => \"wrong-password-xyz\");
print \"AGENT_AUTH_VALID=\", (\$ok ? \$ok : \"FAIL\"), \"\n\";
print \"AGENT_AUTH_INVALID=\", (\$bad ? \$bad : \"FAIL(expected)\"), \"\n\";
'\''"'
```

Saída real:

```
AGENT_AUTH_VALID=william
AGENT_AUTH_INVALID=FAIL(expected)
```

**Resultado:** credencial de agente válida → retorna o login (auth OK →
`SessionCreate` emitiria `SessionID`); credencial inválida → undef →
`SessionCreate.AuthFail`. **INCÓGNITA 1 RESOLVIDA — PRIMARY.**

### Decisão incógnita 1 (PRIMARY)

Mesma operação core `Session::SessionCreate`, transporte `HTTP::REST`,
rota `POST /Session`, **campo de login de agente `UserLogin` + `Password`**.
O sidecar faz `POST {base_url}/nph-genericinterface.pl/Webservice/<Name>/Session`
com `{"UserLogin": login, "Password": pw}`. Resposta com `Data.SessionID` ⇒
credencial válida; `SessionCreate.AuthFail`/`Error`/HTTP 4xx ⇒ inválida; falha
de transporte/5xx ⇒ indisponível. **Idêntico ao contrato D14, só muda o campo.**

Contrato CONGELADO (`integrations/znuny_agent_auth.py`):

```python
class ZnunyUnavailable(RuntimeError): ...

async def authenticate_agent(login: str, password: str) -> bool: ...
#  True  → HTTP 2xx + body com SessionID
#  False → Error / SessionCreate.AuthFail / HTTP 4xx
#  raise ZnunyUnavailable → conexão/timeout/HTTP 5xx
```

> Diferença vs. customer-auth: NÃO há resolução e-mail→login. Agentes Znuny
> autenticam pelo `login` da tabela `users` (não pelo e-mail). O operador
> digita o login de agente. (e-mail→login é específico do portal de cliente.)

---

## INCÓGNITA 2 — Escrita de cliente (CustomerCompany/User) via GI

### Step 2.1 — existe operação GI de escrita de cliente embarcada?

```
ssh gc '... su otrs ... "find /opt/otrs/Kernel/GenericInterface/Operation -iname \"*Customer*\" -o -iname \"*User*\"; ls /opt/otrs/Kernel/GenericInterface/Operation/User/"'
```

Saída real:

```
/opt/otrs/Kernel/GenericInterface/Operation/User
(User/ contém:)  OutOfOffice.pm
```

**Interpretação:** NÃO existe operação GI de escrita de cliente no core.
O namespace `User/` (que é AGENTE, não customer) só traz `OutOfOffice.pm`.
Não há `CustomerCompany::*` nem `CustomerUser::*`. **O GI core não cria cliente.**

### Step 2.2 — a API Perl expõe a escrita? (base para operação custom)

```
ssh gc '... su otrs ... "
  grep -l \"sub CustomerCompanyAdd\" /opt/otrs/Kernel/System/CustomerCompany.pm;
  grep -l \"sub CustomerUserAdd\"    /opt/otrs/Kernel/System/CustomerUser.pm;
  grep -l \"sub SetPassword\"        /opt/otrs/Kernel/System/CustomerUser.pm;"'
```

Saída real:

```
CustomerCompanyAdd: /opt/otrs/Kernel/System/CustomerCompany.pm
CustomerUserAdd:    /opt/otrs/Kernel/System/CustomerUser.pm
SetPassword:        /opt/otrs/Kernel/System/CustomerUser.pm
```

Parâmetros obrigatórios (fonte real):

```perl
# CustomerCompanyAdd: required  CustomerID, UserID   (Source default 'CustomerCompany')
#   úteis: CustomerCompanyName, ValidID
# CustomerUserAdd: wrapper rejeita UserLogin já existente (idempotência);
#   backend exige UserLogin, UserFirstname, UserLastname, UserCustomerID,
#   UserEmail, ValidID, UserID (Source default 'CustomerUser')
# SetPassword: required UserLogin (+ PW)
```

> `UserID` = o AGENTE que executa a ação (auditoria do Znuny). Na operação
> custom usaremos o id do agente autenticado (ou um id de sistema, ex. 1).

### Step 2.3 — overlay `Custom/` já é usado nesta imagem

```
ssh gc '... su otrs ... "ls -R /opt/otrs/Custom/Kernel/"'
```

Saída real:

```
/opt/otrs/Custom/Kernel/System/Cache:
Redis.pm
```

**Interpretação:** o padrão de shipar Perl custom em `Custom/Kernel/...` JÁ
existe na imagem (o `Cache::Redis`). Adicionar uma operação GI custom segue o
mesmo mecanismo (build da imagem `znuny/`), sem hack.

### Decisão incógnita 2 (mecanismo)

O GI core **não** cria cliente → o mecanismo suportado (Spec #0: só GI) é uma
**operação GI custom** que embrulha a API Perl nativa, exposta por um
webservice `GertiAdmin`:

| Operation (custom) | Type | Embrulha |
|---|---|---|
| `CustomerCompanyAdd` | `CustomerCompany::CustomerCompanyAdd` | `Kernel::System::CustomerCompany->CustomerCompanyAdd` |
| `CustomerUserAdd`    | `CustomerUser::CustomerUserAdd`       | `Kernel::System::CustomerUser->CustomerUserAdd` |
| `CustomerUserSetPassword` | `CustomerUser::SetPassword`      | `Kernel::System::CustomerUser->SetPassword` |

Módulos custom em `znuny/Custom/Kernel/GenericInterface/Operation/Customer*/`
(copiados para `/opt/otrs/Custom/...` no build da imagem), + YAML do webservice
`GertiAdmin` importado no deploy (mesmo padrão do webservice de auth, D14).

**⚠️ IMPACTO NO DESENHO (decisão do usuário):** isto adiciona um artefato
**Znuny-side** (Perl custom + import do webservice) que NÃO estava listado como
tarefa no plano. É pré-requisito do e2e (#1G-a só cria login se a operação
existir). Opções para o usuário no checkpoint do spike — ver fim deste doc.

Contrato CONGELADO (`integrations/znuny_customer_admin.py`):

```python
class ZnunyUnavailable(RuntimeError): ...
class ZnunyWriteError(RuntimeError):
    """Rejeição limpa do Znuny (ex.: já existe) — mapeável a 4xx, NÃO 503."""

async def create_customer_company(
    customer_id: str, company_name: str, *, valid: bool = True
) -> str: ...                 # retorna o CustomerID criado/confirmado

async def create_customer_user(
    *, login: str, email: str, first_name: str, last_name: str,
    customer_id: str, valid: bool = True,
) -> str: ...                 # retorna o UserLogin

async def set_password(login: str, password: str) -> None: ...
#  ZnunyUnavailable → conexão/timeout/HTTP 5xx (failure-safe, vira 503)
#  ZnunyWriteError  → Error/4xx limpo do GI (ex.: login duplicado)
```

---

## Resumo — congelado para a Fase 1

| Item | Congelado |
|---|---|
| Auth agente | `Session::SessionCreate` + `UserLogin`/`Password`; `authenticate_agent(login,pw)->bool` (PRIMARY, live-proven) |
| Endpoint GI | `{base_url}/nph-genericinterface.pl/Webservice/<Name>/Session` (mesma `gerti.znuny_instance`, base_url `https://znuny-dev.was.dev.br`) |
| Escrita cliente | operação GI **custom** (webservice `GertiAdmin`) embrulhando a API Perl; contrato `create_customer_company/create_customer_user/set_password` |
| Sessão admin | JWT HS256 `{agent_login, role:"gerti_staff", exp}`, cookie `gsid_adm` (≠ `gsid`), NÃO tenant-scoped |
| Migration | nenhuma nova no #1G-a (admins = agentes Znuny; tenant/branding/role já existem) |

## Decisão para o usuário (checkpoint do spike — antes da Fase 1)

A incógnita 2 mostrou que **criar o login do cliente exige uma operação GI
custom no Znuny** (Perl + webservice `GertiAdmin`). Opções:
- **(A)** Incluir o artefato Znuny-side no #1G-a (módulos custom + import do
  webservice no deploy da Fase 2). e2e completo (onboarding cria login de
  verdade). Escopo maior, mas é o que o spec pede ("sem isso o onboarding não
  cria o login").
- **(B)** #1G-a entrega a UI/API + tenant/branding/papéis no Postgres e
  registra o subdomínio; a criação do CustomerUser/Company no Znuny fica num
  follow-up (#1G-a′), com o write-client em modo "pendente" até o webservice
  existir. e2e prova tudo menos o login Znuny do novo admin.

(Recomendação: A, mas é decisão de escopo do usuário.)
