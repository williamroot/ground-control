<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

interface Saldo { kind: string, remaining: number | null }
interface ContractItem {
  id: string, code: string, type: string, status: string
  starts_on: string, ends_on: string, saldo: Saldo, consumed_percent: number | null
}
interface Alert {
  contract_id: string, code: string, type: string, kind: string
  remaining: number, consumed_percent: number | null, severity: 'warning' | 'critical'
}
interface Dashboard {
  contract_count: number
  balances_by_type: { type: string, kind: string, contract_count: number, total_remaining: number | null }[]
  low_balance_alerts: Alert[]
}

const headers = useRequestHeaders(['cookie'])
const { data: me } = await useAsyncData('me', () =>
  $fetch('/api/portal/me', { headers }).catch(() => null))
if (!me.value) await navigateTo('/login')

const { data: dashboard } = await useAsyncData('dashboard', () =>
  $fetch<Dashboard>('/api/portal/dashboard', { headers }).catch(() => null))
const { data: contracts } = await useAsyncData('contracts', () =>
  $fetch<ContractItem[]>('/api/portal/contracts', { headers })
    .catch(() => [] as ContractItem[]))

const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const TYPE_LABEL: Record<string, string> = {
  hour_bank: 'Banco de horas', credit_brl: 'Crédito (R$)', credit_shared: 'Crédito compartilhado',
  service_count: 'Pacote de serviços', closed_value: 'Valor fechado', saas_product: 'Assinatura',
}
const STATUS_META: Record<string, { label: string, color: 'success' | 'warning' | 'neutral' | 'error' }> = {
  active: { label: 'Ativo', color: 'success' }, suspended: { label: 'Suspenso', color: 'warning' },
  expired: { label: 'Expirado', color: 'error' }, terminated: { label: 'Encerrado', color: 'neutral' },
  draft: { label: 'Rascunho', color: 'neutral' },
}
const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const num = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
function typeLabel(t: string) { return TYPE_LABEL[t] ?? t }
function statusMeta(s: string) { return STATUS_META[s] ?? { label: s, color: 'neutral' as const } }
function saldoBig(c: ContractItem): string {
  const r = c.saldo?.remaining; const kind = c.saldo?.kind
  if (r == null) return '—'
  if (kind === 'hours') return `${num.format(r)} h`
  if (kind === 'brl') return brl.format(r)
  if (kind === 'services') return `${num.format(r)} serviços`
  return num.format(r)
}
function saldoLabel(c: ContractItem): string {
  const kind = c.saldo?.kind
  if (kind === 'hours') return 'Saldo de horas'
  if (kind === 'brl') return 'Saldo disponível'
  if (kind === 'services') return 'Serviços restantes'
  return 'Saldo'
}
function fmtDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-8">
    <header class="mb-8">
      <p class="text-sm text-neutral-500">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-neutral-900">Seus contratos</h1>
      <p class="mt-1 text-sm text-neutral-500">Acompanhe saldos, tipos e vigências dos seus contratos.</p>
    </header>

    <LowBalanceAlerts :alerts="dashboard?.low_balance_alerts ?? []" />

    <UCard v-if="!contracts || contracts.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full text-white"
          :style="{ background: 'var(--brand-primary)' }">
          <UIcon name="i-lucide-file-text" class="h-6 w-6" />
        </span>
        <p class="font-display text-lg font-semibold text-neutral-800">Nenhum contrato ainda</p>
        <p class="max-w-sm text-sm text-neutral-500">Quando um contrato for ativado para você, ele aparecerá aqui.</p>
      </div>
    </UCard>

    <div v-else class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      <NuxtLink v-for="c in contracts" :key="c.id" :to="`/contratos/${c.id}`" class="block">
        <UCard class="h-full transition hover:shadow-md" :ui="{ body: 'space-y-4' }">
          <div class="flex items-start justify-between gap-2">
            <div>
              <p class="font-display text-base font-bold tracking-tight text-neutral-900">{{ c.code }}</p>
              <UBadge color="primary" variant="subtle" size="sm" class="mt-1.5">{{ typeLabel(c.type) }}</UBadge>
            </div>
            <UBadge :color="statusMeta(c.status).color" variant="soft" size="sm">{{ statusMeta(c.status).label }}</UBadge>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-neutral-400">{{ saldoLabel(c) }}</p>
            <p class="font-display text-3xl font-extrabold tracking-tight text-neutral-900">{{ saldoBig(c) }}</p>
            <ProgressBar v-if="c.consumed_percent != null" class="mt-3" :percent="c.consumed_percent" />
          </div>
          <div class="flex items-center gap-1.5 text-xs text-neutral-500">
            <UIcon name="i-lucide-calendar" class="h-3.5 w-3.5" />
            <span>{{ fmtDate(c.starts_on) }} — {{ fmtDate(c.ends_on) }}</span>
          </div>
        </UCard>
      </NuxtLink>
    </div>
  </div>
</template>
