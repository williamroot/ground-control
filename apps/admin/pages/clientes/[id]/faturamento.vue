<script setup lang="ts">
import {
  CHARGE_KINDS,
  chargeKindLabel,
  chargeTotal,
  emptyCharge,
  timeWarning,
  validateCharge,
} from '#imports'

// R6 — a aba de faturamento do cliente. Junta o que a Onda 5 abriu:
//
//  • avisos de cobrança (e-mail/SMS) — R6, com os canais desligados por padrão;
//  • lançamentos avulsos (T-R15.3) — deslocamento, hora extra, despesa;
//  • bolsas de crédito compartilhadas (T-R3.2) — o saldo é do GRUPO;
//  • a chave de aprovação de chamados do cliente (R7).
//
// A tela não recalcula nada de dinheiro: quem decide é o sidecar, e o 422 dele
// é a verdade. A validação daqui existe só para o operador não gastar um
// round-trip descobrindo que esqueceu a descrição.
definePageMeta({ middleware: 'admin-auth' })

const route = useRoute()
const tenantId = route.params.id as string
const headers = useRequestHeaders(['cookie'])
const toast = useToast()

interface BillingConfig {
  email_enabled: boolean
  sms_enabled: boolean
  billing_email: string | null
  billing_phone: string | null
  billing_day: number | null
  notes: string | null
  approval_required: boolean
  // Só leitura: `true` enquanto o SMS não tem provedor real. O PUT recusa
  // campo desconhecido (`extra="forbid"`), então ele NÃO pode voltar no corpo.
  sms_simulated: boolean
}
interface ChargeRow {
  id: number
  contract_id: string
  kind: string
  occurred_at: string
  amount_brl: number
  minutes: number
  recorded_by: string
  glosa_id: string | null
}
interface ContractOption { id: string, code: string, type: string, status: string }
interface PoolRow {
  id: string
  name: string
  total_brl: number
  consumed_brl: number
  remaining_brl: number
  contract_ids: string[]
}
interface ApprovalRow {
  id: string
  znuny_ticket_id: number
  status: string
  requested_by: string
  requested_at: string
}

const { data: config, refresh: refreshConfig } = await useAsyncData(
  `billing-config-${tenantId}`,
  () => $fetch<BillingConfig | null>(`/api/admin/tenants/${tenantId}/billing-config`, { headers })
    .catch(() => null),
)
const { data: charges, refresh: refreshCharges } = await useAsyncData(
  `charges-${tenantId}`,
  () => $fetch<ChargeRow[] | null>(`/api/admin/tenants/${tenantId}/charges`, { headers })
    .catch(() => null),
)
const { data: contracts } = await useAsyncData(
  `charge-contracts-${tenantId}`,
  () => $fetch<ContractOption[] | null>(`/api/admin/tenants/${tenantId}/charges/contracts`, { headers })
    .catch(() => null),
)
const { data: pools, refresh: refreshPools } = await useAsyncData(
  `pools-${tenantId}`,
  () => $fetch<PoolRow[] | null>(`/api/admin/tenants/${tenantId}/credit-pools`, { headers })
    .catch(() => null),
)
// Só leitura: quem decide é o aprovador no portal do cliente, então esta
// lista não tem ação e não precisa de refresh próprio.
const { data: approvals } = await useAsyncData(
  `approvals-${tenantId}`,
  () => $fetch<ApprovalRow[] | null>(`/api/admin/tenants/${tenantId}/approvals`, { headers })
    .catch(() => null),
)

const savingConfig = ref(false)
const draft = ref(emptyCharge())
const savingCharge = ref(false)
const poolName = ref('')
const poolAmount = ref(0)
const savingPool = ref(false)

// Erro só depois que a pessoa mexeu — ver o mesmo cuidado em /licencas.
const touched = ref(false)
watch(draft, () => { touched.value = true }, { deep: true })

const chargeErrors = computed(() => validateCharge(draft.value))
const chargeWarning = computed(() => timeWarning(draft.value))
const total = computed(() => chargeTotal(draft.value))
const kindOptions = CHARGE_KINDS.map(k => ({ label: k.label, value: k.value }))
const contractOptions = computed(() =>
  (contracts.value ?? []).map(c => ({ label: `${c.code} (${c.type})`, value: c.id })))
const sharedContracts = computed(() =>
  (contracts.value ?? []).filter(c => c.type === 'credit_shared'))

function money(v: number): string {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR')
}

async function saveConfig() {
  if (!config.value) return
  savingConfig.value = true
  try {
    // Corpo montado campo a campo, e não `body: config.value`: o schema do
    // sidecar tem `extra="forbid"`, e devolver `sms_simulated` (que é de
    // leitura) faria o PUT inteiro voltar 422.
    await $fetch(`/api/admin/tenants/${tenantId}/billing-config`, {
      method: 'PUT',
      body: {
        email_enabled: config.value.email_enabled,
        sms_enabled: config.value.sms_enabled,
        billing_email: config.value.billing_email || null,
        billing_phone: config.value.billing_phone || null,
        billing_day: config.value.billing_day || null,
        notes: config.value.notes || null,
        approval_required: config.value.approval_required,
      },
    })
    toast.add({ title: 'Configuração salva', color: 'success' })
    await refreshConfig()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    toast.add({
      title: 'Não foi possível salvar',
      // O 422 do sidecar explica, por exemplo, que ligou o SMS sem telefone.
      description: err.data?.detail || 'Falha ao salvar a configuração.',
      color: 'error',
    })
  }
  finally {
    savingConfig.value = false
  }
}

async function addCharge() {
  if (chargeErrors.value.length) return
  savingCharge.value = true
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/charges`, { method: 'POST', body: draft.value })
    toast.add({ title: 'Lançamento registrado', color: 'success' })
    draft.value = emptyCharge()
    await refreshCharges()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    toast.add({
      title: 'Lançamento recusado',
      description: err.data?.detail || 'Falha ao registrar.',
      color: 'error',
    })
  }
  finally {
    savingCharge.value = false
  }
}

async function createPool() {
  if (!poolName.value.trim() || poolAmount.value <= 0) {
    toast.add({ title: 'Informe nome e valor da bolsa', color: 'warning' })
    return
  }
  savingPool.value = true
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/credit-pools`, {
      method: 'POST',
      body: { name: poolName.value.trim(), total_amount_brl: poolAmount.value },
    })
    poolName.value = ''
    poolAmount.value = 0
    toast.add({ title: 'Bolsa criada', color: 'success' })
    await refreshPools()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    toast.add({ title: 'Falha ao criar a bolsa', description: err.data?.detail, color: 'error' })
  }
  finally {
    savingPool.value = false
  }
}

async function linkContract(poolId: string, contractId: string) {
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/credit-pools/${poolId}/contracts`, {
      method: 'POST',
      body: { contract_id: contractId },
    })
    toast.add({ title: 'Contrato ligado à bolsa', color: 'success' })
    await refreshPools()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    toast.add({ title: 'Não foi possível ligar', description: err.data?.detail, color: 'error' })
  }
}

async function unlinkContract(poolId: string, contractId: string) {
  try {
    await $fetch(
      `/api/admin/tenants/${tenantId}/credit-pools/${poolId}/contracts/${contractId}`,
      { method: 'DELETE' },
    )
    await refreshPools()
  }
  catch {
    toast.add({ title: 'Falha ao desligar o contrato', color: 'error' })
  }
}

function contractCode(id: string): string {
  return (contracts.value ?? []).find(c => c.id === id)?.code ?? id.slice(0, 8)
}

const linkTarget = ref<Record<string, string>>({})
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <ULink :to="`/clientes/${tenantId}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <header class="mt-3 mb-6">
      <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
        Faturamento
      </h1>
      <p class="mt-1 text-sm text-muted">
        Avisos de cobrança, lançamentos avulsos, bolsas de crédito e aprovação de chamados.
      </p>
    </header>

    <!-- Avisos + aprovação -->
    <UCard v-if="config" class="mb-6">
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Avisos e fluxo</h2>
      </template>

      <div class="space-y-4">
        <div class="flex flex-wrap items-end gap-3">
          <USwitch v-model="config.email_enabled" label="Avisar por e-mail" />
          <UFormField label="E-mail de cobrança" class="flex-1 min-w-[240px]">
            <UInput v-model="config.billing_email" placeholder="financeiro@cliente.com.br" class="w-full" />
          </UFormField>
        </div>

        <div class="flex flex-wrap items-end gap-3">
          <USwitch v-model="config.sms_enabled" label="Avisar por SMS" />
          <UFormField label="Celular" class="flex-1 min-w-[240px]">
            <UInput v-model="config.billing_phone" placeholder="+55 31 99999-0000" class="w-full" />
          </UFormField>
        </div>
        <p v-if="config.sms_simulated" class="text-xs text-muted">
          O SMS ainda sai em <strong>modo simulado</strong> — a mensagem vai para o log do
          servidor, com o número mascarado, até um provedor ser contratado.
        </p>

        <div class="flex flex-wrap items-end gap-3">
          <UFormField label="Dia de faturamento" help="1 a 28 — 29 a 31 não existem em todo mês.">
            <UInput v-model.number="config.billing_day" type="number" min="1" max="28" class="w-32" />
          </UFormField>
          <UFormField label="Observações" class="flex-1 min-w-[240px]">
            <UInput v-model="config.notes" placeholder="Nota interna sobre a cobrança" class="w-full" />
          </UFormField>
        </div>

        <USeparator />

        <USwitch
          v-model="config.approval_required"
          label="Exigir aprovação antes de atender"
        />
        <p class="text-xs text-muted">
          Com isto ligado, todo chamado deste cliente nasce aguardando decisão de um
          aprovador e nenhum agente o atende antes disso.
        </p>
      </div>

      <template #footer>
        <UButton :loading="savingConfig" icon="i-lucide-save" label="Salvar" @click="saveConfig" />
      </template>
    </UCard>

    <!-- Fila de aprovação -->
    <UCard v-if="approvals && approvals.length" class="mb-6">
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">
          Aguardando aprovação do cliente ({{ approvals.length }})
        </h2>
      </template>
      <ul class="divide-y divide-default text-sm">
        <li v-for="a in approvals" :key="a.id" class="flex items-center justify-between py-2">
          <span class="font-mono text-highlighted">#{{ a.znuny_ticket_id }}</span>
          <span class="text-muted">pedido por {{ a.requested_by }} em {{ fmtDate(a.requested_at) }}</span>
        </li>
      </ul>
      <template #footer>
        <p class="text-xs text-muted">
          Quem decide é o aprovador do cliente, no portal dele. Esta lista existe para a Gerti
          saber o que está parado esperando resposta.
        </p>
      </template>
    </UCard>

    <!-- Lançamentos avulsos -->
    <UCard class="mb-6">
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Lançamento avulso</h2>
      </template>

      <div class="grid gap-3 sm:grid-cols-2">
        <UFormField label="Contrato">
          <USelectMenu v-model="draft.contract_id" :items="contractOptions" value-key="value" class="w-full" />
        </UFormField>
        <UFormField label="Tipo">
          <USelectMenu v-model="draft.kind" :items="kindOptions" value-key="value" class="w-full" />
        </UFormField>
        <UFormField label="Descrição" class="sm:col-span-2">
          <UInput v-model="draft.description" placeholder="Deslocamento até a filial Centro" class="w-full" />
        </UFormField>
        <UFormField label="Valor unitário (R$)">
          <UInput v-model.number="draft.amount_brl" type="number" step="0.01" class="w-full" />
        </UFormField>
        <UFormField label="Quantidade">
          <UInput v-model.number="draft.quantity" type="number" step="1" class="w-full" />
        </UFormField>
        <UFormField label="Minutos (opcional)" help="Só preencha se este lançamento deve consumir banco de horas.">
          <UInput v-model.number="draft.minutes" type="number" step="1" class="w-full" />
        </UFormField>
        <UFormField label="Data">
          <UInput v-model="draft.occurred_on" type="date" class="w-full" />
        </UFormField>
      </div>

      <UAlert
        v-if="chargeWarning"
        class="mt-4"
        color="warning"
        variant="soft"
        icon="i-lucide-alert-triangle"
        :description="chargeWarning"
      />
      <ul v-if="touched && chargeErrors.length" class="mt-3 list-disc pl-5 text-sm text-error">
        <li v-for="err in chargeErrors" :key="err">{{ err }}</li>
      </ul>

      <template #footer>
        <div class="flex items-center justify-between">
          <span class="text-sm text-muted">Total: <strong class="text-highlighted">{{ money(total) }}</strong></span>
          <UButton
            :loading="savingCharge"
            :disabled="chargeErrors.length > 0"
            icon="i-lucide-plus"
            label="Lançar"
            @click="addCharge"
          />
        </div>
      </template>
    </UCard>

    <UCard v-if="charges && charges.length" class="mb-6">
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Lançamentos registrados</h2>
      </template>
      <table class="w-full text-sm">
        <thead class="text-left text-xs uppercase text-muted">
          <tr>
            <th class="py-2">Data</th>
            <th class="py-2">Tipo</th>
            <th class="py-2">Contrato</th>
            <th class="py-2 text-right">Valor</th>
            <th class="py-2">Lançado por</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in charges" :key="c.id" class="border-t border-default">
            <td class="py-2 text-muted">{{ fmtDate(c.occurred_at) }}</td>
            <td class="py-2">
              {{ chargeKindLabel(c.kind) }}
              <UBadge v-if="c.glosa_id" color="warning" variant="soft" size="sm" class="ml-1">
                contestado
              </UBadge>
            </td>
            <td class="py-2 font-mono text-xs text-muted">{{ contractCode(c.contract_id) }}</td>
            <td class="py-2 text-right font-semibold text-highlighted">{{ money(c.amount_brl) }}</td>
            <td class="py-2 text-muted">{{ c.recorded_by }}</td>
          </tr>
        </tbody>
      </table>
    </UCard>

    <!-- Bolsas compartilhadas -->
    <UCard>
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Bolsa de crédito compartilhada</h2>
      </template>

      <p class="mb-4 text-sm text-muted">
        A matriz compra o crédito e as filiais consomem do mesmo bolo. Só contratos do tipo
        <strong>crédito compartilhado</strong> entram numa bolsa.
      </p>

      <div class="mb-5 flex flex-wrap items-end gap-3">
        <UFormField label="Nome da bolsa" class="flex-1 min-w-[200px]">
          <UInput v-model="poolName" placeholder="Bolsa matriz 2026" class="w-full" />
        </UFormField>
        <UFormField label="Valor total (R$)">
          <UInput v-model.number="poolAmount" type="number" step="0.01" class="w-full" />
        </UFormField>
        <UButton :loading="savingPool" icon="i-lucide-wallet" label="Criar bolsa" @click="createPool" />
      </div>

      <div v-if="!pools || pools.length === 0" class="text-sm text-muted">
        Nenhuma bolsa criada.
      </div>

      <div v-for="p in pools" :key="p.id" class="mb-4 rounded-xl border border-default p-4">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h3 class="font-semibold text-highlighted">{{ p.name }}</h3>
          <span class="text-sm">
            <span class="text-muted">Disponível</span>
            <strong class="ml-1 text-highlighted">{{ money(p.remaining_brl) }}</strong>
            <span class="text-muted"> de {{ money(p.total_brl) }}</span>
          </span>
        </div>

        <ul v-if="p.contract_ids.length" class="mt-3 space-y-1 text-sm">
          <li v-for="cid in p.contract_ids" :key="cid" class="flex items-center justify-between">
            <span class="font-mono text-xs">{{ contractCode(cid) }}</span>
            <UButton
              size="xs"
              color="neutral"
              variant="ghost"
              icon="i-lucide-unlink"
              label="Desligar"
              @click="unlinkContract(p.id, cid)"
            />
          </li>
        </ul>
        <p v-else class="mt-3 text-sm text-muted">Nenhum contrato ligado — a bolsa está intacta.</p>

        <div v-if="sharedContracts.length" class="mt-3 flex flex-wrap items-end gap-2">
          <USelectMenu
            v-model="linkTarget[p.id]"
            :items="sharedContracts.map(c => ({ label: c.code, value: c.id }))"
            value-key="value"
            placeholder="Escolha o contrato"
            class="min-w-[200px]"
          />
          <UButton
            size="sm"
            variant="soft"
            icon="i-lucide-link"
            label="Ligar à bolsa"
            :disabled="!linkTarget[p.id]"
            @click="linkContract(p.id, linkTarget[p.id]!)"
          />
        </div>
      </div>
    </UCard>
  </div>
</template>
