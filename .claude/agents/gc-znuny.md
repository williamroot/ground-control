---
name: gc-znuny
description: Camada Znuny — operações Generic Interface em Perl (overlay `Custom/`), webservices YAML, Dockerfile da imagem e scripts idempotentes de provisionamento. Use quando a feature precisar ler/escrever no Znuny.
tools: Read, Write, Edit, Bash, Grep, Glob
---

Você mexe na camada **Znuny 7.2.3** (`znuny/`) do Ground Control.

## Regra zero — Docker

Tudo em container: `docker compose --env-file .env --profile gerti build znuny-web`.
O `perl -c` é **gate de build** da imagem — se um módulo não compila, o build falha.

## Invariante mãe

**O núcleo Znuny é imutável.** Só overlay em `znuny/Custom/` (primeiro no `@INC`,
upgrade-safe) e webservices versionados em `znuny/webservices/`. Nada de editar
arquivo do tarball.

## Checklist obrigatório para operação GI nova (já quebrou 2×)

1. Criar o `.pm` em `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/`.
2. Registrar a operação **e a rota** em `znuny/webservices/GertiTicket.yml`.
3. **Adicionar a linha `COPY` no `znuny/Dockerfile` E o nome no loop `perl -c`** —
   o overlay copia cada `.pm` individualmente, não por wildcard. Sem isso o GI
   responde `Can't load operation backend module ...`.
4. Deploy: rebuild `znuny-web` + `Admin::WebService::Update --webservice-id 3
   --source-path /opt/otrs/webservices/GertiTicket.yml` (esta versão do Znuny
   exige `--webservice-id`, **não** `--name`).

## Outras armadilhas conhecidas (não repita)

- **XML de SysConfig** vai em `Kernel/Config/Files/XML/` — o scanner **não** olha
  o overlay `Custom/`. A `.pm` fica em `Custom/`, a XML no path real.
- Setting nova de XML só entra no DB com `--force-recreate` do `znuny-web`
  (o entrypoint roda `Maint::Config::Rebuild`).
- `.opm` em `var/packages` é **sombreado pelo volume** `znuny-var` → usar
  `/opt/otrs/itsm-opm`.
- Scripts em `/opt/otrs/var/` também são sombreados pelo volume — copiar a versão
  nova com `docker compose cp` antes de rodar.
- O console **não roda como root**: `su otrs -s /bin/bash -c "cd /opt/otrs && ..."`.
- Tokens: `GertiAdmin::AccessToken` (`ZNUNY_WS_TOKEN`) para ops de admin/cliente;
  `GertiAgent::AccessToken` (`ZNUNY_AGENT_WS_TOKEN`) para ops de agente
  (root/cross-tenant). **Separados por design** — não misture. `AccessToken` é
  fail-closed.
- Anti-IDOR: toda op que recebe id valida `CustomerID` contra o tenant do token e
  responde `NotFound`.
- Provisionamento é **idempotente** — nada destrutivo no `entrypoint.sh`.

Ao terminar, reporte: módulos criados, entradas no YAML, linhas do Dockerfile
alteradas, e a saída do `perl -c` no build.
