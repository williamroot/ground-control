<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'
import { statusColor, statusLabel, typeLabel } from '~/components/contract/labels'

definePageMeta({ middleware: 'auth' }) // #1H: sessão + papel admin

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

// Auth + papel admin garantidos pela middleware nomeada `auth` (definePageMeta, #1H).
const headers = useRequestHeaders(['cookie'])
const { data: dashboard } = await useAsyncData('dashboard', () =>
  $fetch<Dashboard>('/api/portal/dashboard', { headers }).catch(() => null))
const { data: contracts } = await useAsyncData('contracts', () =>
  $fetch<ContractItem[]>('/api/portal/contracts', { headers })
    .catch(() => [] as ContractItem[]))

const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const num = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
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
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">Seus contratos</h1>
      <p class="mt-1 text-sm text-muted">Acompanhe saldos, tipos e vigências dos seus contratos.</p>
    </header>

    <LowBalanceAlerts :alerts="dashboard?.low_balance_alerts ?? []" />

    <UCard v-if="!contracts || contracts.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <span
class="inline-flex h-12 w-12 items-center justify-center rounded-full text-white"
          :style="{ background: 'var(--brand-primary)' }">
          <UIcon name="i-lucide-file-text" class="h-6 w-6" />
        </span>
        <p class="font-display text-lg font-semibold text-highlighted">Nenhum contrato ainda</p>
        <p class="max-w-sm text-sm text-muted">Quando um contrato for ativado para você, ele aparecerá aqui.</p>
      </div>
    </UCard>

    <div v-else class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      <NuxtLink v-for="c in contracts" :key="c.id" :to="`/contratos/${c.id}`" class="block">
        <UCard class="h-full transition hover:shadow-md" :ui="{ body: 'space-y-4' }">
          <div class="flex items-start justify-between gap-2">
            <div>
              <p class="font-display text-base font-bold tracking-tight text-highlighted">{{ c.code }}</p>
              <UBadge color="primary" variant="subtle" size="sm" class="mt-1.5">{{ typeLabel(c.type) }}</UBadge>
            </div>
            <UBadge :color="statusColor(c.status)" variant="soft" size="sm">{{ statusLabel(c.status) }}</UBadge>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-dimmed">{{ saldoLabel(c) }}</p>
            <p class="font-display text-3xl font-extrabold tracking-tight text-highlighted">{{ saldoBig(c) }}</p>
            <ProgressBar v-if="c.consumed_percent != null" class="mt-3" :percent="c.consumed_percent" />
          </div>
          <div class="flex items-center gap-1.5 text-xs text-muted">
            <UIcon name="i-lucide-calendar" class="h-3.5 w-3.5" />
            <span>{{ fmtDate(c.starts_on) }} — {{ fmtDate(c.ends_on) }}</span>
          </div>
        </UCard>
      </NuxtLink>
    </div>
  </div>
</template>
