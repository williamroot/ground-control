# Ground Control — Instância de DEMONSTRAÇÃO

> ⚠️ **INSTÂNCIA DE DEMONSTRAÇÃO — credenciais descartáveis.**
> Todas as senhas abaixo são públicas e padronizadas só para apresentação.
> **TROQUE TODAS antes de qualquer uso real / produção.** Não há dado sensível aqui:
> empresa, pessoas, CNPJ e tickets são **fictícios**.

Cenário: a **Gerti** (MSP) operando o Service Desk no Znuny para um cliente
fictício, demonstrando a substituição do Tiflux. Tudo é semeado de forma
**idempotente** por [`scripts/seed-demo.sh`](../scripts/seed-demo.sh).

---

## 1. A empresa fictícia (o cliente / tenant)

| Campo | Valor |
|---|---|
| Razão social | **Móveis Aurora Indústria e Comércio Ltda.** |
| Nome fantasia | **Aurora Móveis** |
| CustomerID (Znuny) | `AURORA` |
| CNPJ (fictício) | 18.472.366/0001-90 |
| Ramo | Fabricante de móveis planejados |
| Endereço | Rua dos Marceneiros, 1240 — Distrito Industrial |
| Cidade/UF | Bento Gonçalves/RS — CEP 95700-000 |
| Telefone | (54) 3452-7700 |
| Site / domínio de e-mail | www.auroramoveis.com.br · `@auroramoveis.com.br` |
| Relação com a MSP | Cliente da Gerti desde 2023 — contrato Suporte Gerenciado (SLA Ouro) |

Bento Gonçalves/RS é um polo moveleiro real — a identidade é coerente e
"passa no teste de realidade" sem ser uma empresa existente.

---

## 2. Credenciais

URLs da instância viva:

- **Agentes (técnicos/admin):** <https://znuny-dev.was.dev.br/znuny/index.pl>
- **Clientes (portal Znuny):** <https://znuny-dev.was.dev.br/znuny/customer.pl>

### 2.1 Agentes (equipe Gerti / MSP)

| Login | Nome | Papel | E-mail | Senha demo | O que enxerga |
|---|---|---|---|---|---|
| `william` | William Alves | **Owner / Admin** | williamalvesroot@gmail.com | `Gerti@Demo2026` | Tudo: admin, todas as filas, configuração, stats |
| `bruno.cardoso` | Bruno Cardoso | Suporte N1 | bruno.cardoso@gerti.com.br | `Gerti@Demo2026` | Filas de suporte, triagem, incidentes simples |
| `patricia.menezes` | Patrícia Menezes | Suporte N1 | patricia.menezes@gerti.com.br | `Gerti@Demo2026` | Filas de suporte, triagem, incidentes simples |
| `rafael.tavares` | Rafael Tavares | Suporte N2 (especialista) | rafael.tavares@gerti.com.br | `Gerti@Demo2026` | Escalonamento técnico, infra/redes |
| `diego.fontana` | Diego Fontana | Field Service (campo) | diego.fontana@gerti.com.br | `Gerti@Demo2026` | Atendimentos on-site / visitas técnicas |

> O agente **William** tem `rw` nos grupos `admin`, `users` e `stats` + role
> *Administradores* — é o usuário de demonstração com poder total.

### 2.2 Customer users (colaboradores da Aurora Móveis)

| Login | Nome | Cargo | E-mail | Senha demo |
|---|---|---|---|---|
| `mariana.bianchi` | Mariana Bianchi | Coordenadora Administrativa | mariana.bianchi@auroramoveis.com.br | `Aurora@Demo2026` |
| `eduardo.salvi` | Eduardo Salvi | Gerente de TI | eduardo.salvi@auroramoveis.com.br | `Aurora@Demo2026` |
| `carla.dorneles` | Carla Dorneles | Analista Financeiro | carla.dorneles@auroramoveis.com.br | `Aurora@Demo2026` |
| `fernando.rech` | Fernando Rech | Supervisor de Produção | fernando.rech@auroramoveis.com.br | `Aurora@Demo2026` |
| `juliana.peruzzo` | Juliana Peruzzo | Assistente de RH | juliana.peruzzo@auroramoveis.com.br | `Aurora@Demo2026` |

Todos vinculados ao CustomerID `AURORA` — veem no portal apenas os chamados
da própria empresa.

---

## 3. Inventário semeado

| Entidade | Quantidade | Detalhe |
|---|---|---|
| Roles (perfis de agente) | 4 | Administradores, Suporte N1, Suporte N2, Field Service |
| Agentes | 5 | 1 admin + 2×N1 + 1×N2 + 1×Field |
| Empresa cliente | 1 | Móveis Aurora (`AURORA`) |
| Customer users | 5 | colaboradores da Aurora |
| Filas | 5 | `Suporte`, `Suporte::N1`, `Suporte::N2`, `Field Service`, `Financeiro` (+ Postmaster/Raw/Junk/Misc default) |
| Serviços | 11 | Infraestrutura(+Servidores,+Backup), Microsoft 365(+E-mail), Rede(+VPN,+Wi-Fi), Hardware(+Impressoras), Acesso e Senhas |
| SLAs | 3 | SLA Bronze (8h/48h), SLA Prata (4h/24h), SLA Ouro (1h/8h) |
| Tickets | 17 | ver distribuição abaixo |
| Artigos | 48 | múltiplos por ticket — cliente abre, técnico responde, notas internas |
| Apontamento de horas | 15 tickets · 630 min | `TimeUnits` lançados contra artigos do técnico |

**Tickets por estado:**

| Estado | Qtde |
|---|---|
| closed successful | 8 |
| open | 4 |
| pending reminder | 3 |
| new | 2 |

Datas de criação espalhadas ~30 dias (idade realista para dashboards).
Pelo menos 3 chamados encerrados têm ida-e-volta completa
(cliente → técnico → cliente → nota interna → encerramento).

---

## 4. Roteiro de apresentação (5–10 min)

1. **Abrir o console do agente.** <https://znuny-dev.was.dev.br/znuny/index.pl> —
   logar como `william` / `Gerti@Demo2026`.
   *Fala:* "Este é o console da operação da Gerti. O William é o administrador
   da plataforma e enxerga todas as filas e todos os clientes."

2. **Visão de filas.** Menu *Filas* (Queue View). Mostrar a árvore
   `Suporte::N1`, `Suporte::N2`, `Field Service`, `Financeiro`.
   *Fala:* "A operação é organizada em níveis, igual numa MSP de verdade:
   N1 faz a triagem, N2 é o especialista, Field Service vai a campo."

3. **Abrir um chamado de cliente.** Entrar na fila `Suporte::N1` e abrir
   *"Não consigo acessar o e-mail no Outlook"* (cliente: Mariana Bianchi).
   *Fala:* "Olha o histórico: a cliente abriu, o Bruno (N1) respondeu,
   resolveu a senha expirada do M365 e ainda registrou uma nota interna
   sugerindo melhoria. Tudo rastreado."

4. **Mostrar SLA e tempo.** No ticket, destacar o SLA (Ouro), o serviço
   (Microsoft 365::E-mail) e o **apontamento de horas** (aba de tempo).
   *Fala:* "Cada atendimento tem SLA contratado e horas apontadas — é isso
   que alimenta faturamento e relatórios de consumo do contrato."

5. **Responder como técnico (ao vivo).** Em um chamado **aberto**
   (ex.: *"Lentidão na VPN para acesso ao ERP"*, owner Rafael), usar
   *Responder* e adicionar uma resposta ou nota interna.
   *Fala:* "O técnico responde aqui dentro; o cliente recebe e acompanha
   pelo portal — sem e-mail solto, tudo no fluxo."

6. **Painel / visão geral.** Voltar ao *Dashboard*. Mostrar chamados por
   estado, idade, distribuição entre técnicos.
   *Fala:* "O gestor da MSP tem a foto da operação em tempo real:
   o que está aberto, pendente, atrasando."

7. **Trocar para a visão do cliente.** Abrir aba anônima →
   <https://znuny-dev.was.dev.br/znuny/customer.pl> →
   logar como `eduardo.salvi` / `Aurora@Demo2026`.
   *Fala:* "Agora sou o cliente — o Gerente de TI da Aurora Móveis."

8. **Acompanhar chamado pelo portal.** Mostrar a lista de chamados da
   empresa, abrir um deles, ver o andamento e a possibilidade de responder.
   *Fala:* "O cliente abre, acompanha e interage pelo portal. Ele só vê os
   chamados da própria empresa — multi-tenant na prática."

9. **Fechar a narrativa.** *Fala:* "Mesmo cenário que o Tiflux entrega hoje
   — filas, SLA, contrato, portal do cliente — mas em base própria,
   white-label e sem dependência de SaaS de terceiros."

---

## 5. Como (re)semear, verificar e resetar

Tudo roda na VPS, dentro de `~/ground-control`, com a stack de pé.

```bash
# 1. Atualizar o repo na VPS
ssh ubuntu@100.99.49.110
cd ~/ground-control && git pull

# 2. Semear / re-semear (IDEMPOTENTE — pode rodar quantas vezes quiser)
./scripts/seed-demo.sh

# 3. Só rodar as verificações end-to-end (sem semear de novo)
./scripts/seed-demo.sh --verify

# 4. Resetar SOMENTE os dados de demo (tickets + empresa + customer users).
#    Agentes/filas/SLAs/serviços são compartilhados e preservados.
./scripts/seed-demo.sh --reset      # pede confirmação "SIM"
```

- **Idempotência:** o seed verifica-antes-de-criar cada entidade. Reexecutar
  não duplica nada e não gera erro — só reporta `= já existe`.
- **Senhas:** o seed **re-aplica** as senhas documentadas a cada execução,
  então rodar de novo "conserta" credenciais que tenham sido trocadas.
- **Reset total da stack** (destrói o banco inteiro, não só a demo):
  `make reset` na raiz do repo — só em recriação consciente.

O motor é [`scripts/seed-demo.pl`](../scripts/seed-demo.pl) (API nativa do
Znuny: Ticket/Article/CustomerUser/Queue/Service/SLA/User/Group), executado
dentro do container `znuny-web` como usuário `otrs`. O helper
[`scripts/seed-authcheck.pl`](../scripts/seed-authcheck.pl) prova as
credenciais via `Kernel::System::Auth` / `CustomerAuth`.
