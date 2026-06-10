# Como testar o Agente de Inventário (#1R) — passo a passo

Guia prático para testar o auto-registro de equipamentos no CMDB pelo agente.
Ambiente: **staging**. Credenciais demo são públicas (somente para teste).

## Visão geral do que você vai testar
Você atua como **operador MSP** (no console), gera um comando de instalação, roda numa
**máquina de teste** (que simula o computador do cliente), e confirma que o equipamento
entra **sozinho** no inventário do cliente certo (Aurora) — com as travas de segurança.

| Papel | URL | Login |
|-------|-----|-------|
| Console (operador MSP) | https://gerti.was.dev.br | `william` / `Gerti@Demo2026` |
| Portal do cliente (Aurora) | https://aurora.was.dev.br | `eduardo.salvi@auroramoveis.com.br` / `Aurora@Demo2026` |
| Servidor do agente | https://api-dev.was.dev.br | (sem login — autentica por token) |

**Máquina de teste:** qualquer uma destas serve:
- uma **VM/host Linux** (teste completo, com serviço systemd), ou
- **Docker** em qualquer SO (teste rápido do fluxo, sem systemd) — o mais fácil.

---

## Parte 1 — Gerar o comando de instalação (no console)

1. Acesse **https://gerti.was.dev.br** e entre com `william` / `Gerti@Demo2026`.
2. Vá em **Clientes** → abra **Aurora Móveis**.
3. Clique em **Agentes**.
4. Em **"Instalar agente"**, clique em **Gerar token de instalação**.
5. Copie o **comando** que aparece (algo como):
   ```sh
   curl https://api-dev.was.dev.br/v1/agent/install.sh | sh -s -- \
     --enroll-token=gcat_xxxxxxxxxxxxxxxxxxxx --server=https://api-dev.was.dev.br
   ```
   > O token aparece **uma única vez**. Se perder, gere outro (e desabilite o anterior).

---

## Parte 2 — Instalar o agente na máquina de teste

### Opção A — Máquina/VM Linux real (teste completo, com serviço)
Cole e rode o comando do passo 1 **como root** na máquina:
```sh
curl https://api-dev.was.dev.br/v1/agent/install.sh | sudo sh -s -- \
  --enroll-token=<SEU_TOKEN> --server=https://api-dev.was.dev.br
```
Isso baixa o binário, faz o enroll e instala o serviço `gc-agent` (systemd).
Confira o serviço:
```sh
systemctl status gc-agent
journalctl -u gc-agent --no-pager | tail
```

### Opção B — Docker (teste rápido do fluxo, em qualquer SO)
Não precisa de VM. Numa máquina com Docker, rode (troque `<SEU_TOKEN>`):
```sh
docker run --rm debian:bookworm-slim sh -c '
  apt-get update -qq && apt-get install -y -qq ca-certificates curl >/dev/null
  curl -fsS https://api-dev.was.dev.br/v1/agent/download/linux-amd64 -o /usr/local/bin/gc-agent
  chmod +x /usr/local/bin/gc-agent
  gc-agent enroll --server https://api-dev.was.dev.br --enroll-token <SEU_TOKEN> --config /tmp/agent.conf
  echo "--- agent.conf (note: SEM enroll_token, só a credencial) ---"; cat /tmp/agent.conf
  echo "--- heartbeat por 8s ---"; timeout 8 gc-agent run --config /tmp/agent.conf
'
```
Você deve ver `enroll: OK (status=active, agent_id=...)` e o `agent.conf` com `agent_id` +
`agent_secret` (e **sem** o `enroll_token` — ele é descartado após a troca).

---

## Parte 3 — Confirmar o registro

### No console (operador)
- Volte em **Aurora → Agentes**. O dispositivo aparece na lista com status **● Ativo**,
  o hostname da máquina, o SO e o "último contato" (heartbeat).

### No inventário do cliente (portal Aurora)
- Acesse **https://aurora.was.dev.br** com `eduardo.salvi@auroramoveis.com.br` / `Aurora@Demo2026`.
- Vá em **Ativos**. O equipamento que você acabou de instalar está lá, com SO/CPU/memória/disco
  coletados automaticamente pelo agente.

✅ **Pronto** — o equipamento se registrou sozinho no inventário da Aurora.

---

## Parte 4 — Testar a segurança (o ponto importante)

### 4.1 "Só vai pro cliente certo"
O token é da **Aurora**. O equipamento entrou **só** no inventário da Aurora — nunca em outro
cliente. (Tecnicamente: o servidor resolve o cliente a partir do token, o agente não escolhe.)
Para conferir: entre no portal da **TechNova** (se tiver acesso) — o equipamento da Aurora
**não** aparece lá.

### 4.2 Aprovação de novos equipamentos (trava anti-token-vazado)
1. No console, gere um token com **limite de 1 registro** (campo "máx. registros" = 1).
2. Registre **dois** equipamentos diferentes com esse token (rode a Opção B em duas máquinas/
   containers, ou mude o fingerprint).
3. O **segundo** entra como **● Pendente** (não vai pro inventário) até você clicar **Aprovar**
   no console. Aprove e confirme que ele aparece nos Ativos.

### 4.3 Revogar um equipamento
1. No console, no dispositivo, clique **Revogar**.
2. O agente daquela máquina, no próximo heartbeat, recebe **401** e **para** sozinho
   (em VM: `journalctl -u gc-agent` mostra "credencial revogada"; o serviço encerra).

### 4.4 Rotacionar/desabilitar o token
1. No console, **desabilite** (ou rotacione) o token de instalação.
2. Tente registrar um equipamento novo com o token antigo → é **rejeitado (401)**.
   (Equipamentos já registrados continuam funcionando com a credencial própria deles.)

---

## Solução de problemas

| Sintoma | Causa provável / o quê fazer |
|---------|------------------------------|
| `enroll: 401` | Token errado, desabilitado ou expirado. Gere outro no console. |
| Equipamento fica **Pendente** e não entra | Limite do token atingido (ou token expirado) → **Aprovar** no console. |
| `curl: SSL certificate problem` | Falta `ca-certificates` na máquina (a Opção B já instala). Em VM: `apt-get install -y ca-certificates`. |
| Não aparece em **Ativos** mas aparece em **Agentes como Ativo** | Aguarde alguns segundos / recarregue; o ativo é escrito no enroll. Se persistir, ver `journalctl -u gc-agent`. |
| Quero reinstalar a mesma máquina | É **idempotente** — re-rodar o comando atualiza o mesmo equipamento (não duplica). |

## Limpeza (após o teste)
- No console, **revogue** os dispositivos de teste e **desabilite** o token.
- (Opcional) Os Config Items de teste podem ser removidos na interface do Znuny
  (https://znuny-dev.was.dev.br) em ITSM → Config Items.

---

## Referência rápida (terminal, sem UI)
Gerar token via API e registrar — útil para automação/CI:
```sh
# 1) token (como operador) — precisa do cookie de sessão admin do console
#    (mais simples: gere pela UI em Aurora → Agentes)
# 2) registrar:
gc-agent enroll --server https://api-dev.was.dev.br --enroll-token <TOKEN> --config ./agent.conf
gc-agent run --config ./agent.conf     # loop de heartbeat (Ctrl-C para sair)
```
Endpoints públicos: `GET /v1/agent/install.sh?server=…`, `GET /v1/agent/download/{linux-amd64|windows-amd64.exe|darwin-arm64}`, `POST /v1/agent/enroll`, `POST /v1/agent/heartbeat`.
