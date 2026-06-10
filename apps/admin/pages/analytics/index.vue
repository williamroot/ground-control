<script setup lang="ts">
import type { DashboardMetrics } from '#shared/metrics'
import { csatBars, ticketStateSegments, ticketVolumePoints } from '#shared/metrics'

// Analytics do console (#1O) — agente, cross-tenant. Seletor de tenant (lista de
// /v1/admin/tenants) + opção "Todos" (agrega client-side os tenants). Mesmos
// charts do portal. H8: estados em cores semânticas, marca só na navegação.
definePageMeta({ middleware: 'admin-auth' })

interface TenantSummary { id: string, trade_name: string }

const headers = useRequestHeaders(['cookie'])

const { data: tenants } = await useAsyncData('analytics-tenants', () =>
  $fetch<TenantSummary[]>('/api/admin/tenants', { headers }).catch(() => [] as TenantSummary[]))

const ALL = '__all__'
const options = computed(() => [
  { label: 'Todos os clientes', value: ALL },
  ...(tenants.value ?? []).map(t => ({ label: t.trade_name, value: t.id })),
])
const selected = ref<string>(ALL)

function emptyMetrics(periodDays: number): DashboardMetrics {
  return {
    period_days: periodDays,
    tickets: { by_state: {}, by_priority: {}, by_day: [], sla_breached: 0, sla_at_risk: 0, total: 0 },
    csat: { avg: null, count: 0, distribution: {} },
    hours: { total_minutes: 0, total_hours: 0 },
    balance: { contract_count: 0, contracts: [], low_balance_alerts: [] },
  }
}

// Agrega N payloads de tenant num só (modo "Todos"). CSAT vira média ponderada
// pela contagem; tickets/horas/saldo somam; by_day soma por data.
function aggregate(list: DashboardMetrics[]): DashboardMetrics {
  const out = emptyMetrics(list[0]?.period_days ?? 30)
  let csatSum = 0
  let csatN = 0
  const byDay = new Map<string, number>()
  for (const m of list) {
    if (m.tickets) {
      out.tickets!.sla_breached += m.tickets.sla_breached
      out.tickets!.sla_at_risk += m.tickets.sla_at_risk
      out.tickets!.total += m.tickets.total
      for (const [k, v] of Object.entries(m.tickets.by_state))
        out.tickets!.by_state[k] = (out.tickets!.by_state[k] ?? 0) + v
      for (const [k, v] of Object.entries(m.tickets.by_priority))
        out.tickets!.by_priority[k] = (out.tickets!.by_priority[k] ?? 0) + v
      for (const d of m.tickets.by_day)
        byDay.set(d.date, (byDay.get(d.date) ?? 0) + d.count)
    }
    if (m.csat.avg != null && m.csat.count > 0) {
      csatSum += m.csat.avg * m.csat.count
      csatN += m.csat.count
    }
    out.csat.count += m.csat.count
    for (const [k, v] of Object.entries(m.csat.distribution))
      out.csat.distribution[k] = (Number(out.csat.distribution[k] ?? 0)) + Number(v)
    out.hours.total_minutes += m.hours.total_minutes
    out.hours.total_hours += m.hours.total_hours
    out.balance.contract_count += m.balance.contract_count
  }
  out.csat.avg = csatN > 0 ? csatSum / csatN : null
  out.tickets!.by_day = [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, count]) => ({ date, count }))
  out.hours.total_hours = Math.round(out.hours.total_hours * 100) / 100
  return out
}

const { data: metrics, status } = await useAsyncData<DashboardMetrics | null>(
  'admin-analytics',
  async () => {
    const sel = selected.value
    if (sel === ALL) {
      const ids = (tenants.value ?? []).map(t => t.id)
      if (!ids.length) return emptyMetrics(30)
      const results = await Promise.all(
        ids.map(id => $fetch<DashboardMetrics | null>('/api/admin/analytics', {
          headers, query: { tenant_id: id },
        }).catch(() => null)),
      )
      const ok = results.filter((r): r is DashboardMetrics => r != null)
      return ok.length ? aggregate(ok) : emptyMetrics(30)
    }
    return $fetch<DashboardMetrics | null>('/api/admin/analytics', {
      headers, query: { tenant_id: sel },
    }).catch(() => null)
  },
  { watch: [selected] },
)

const isLoading = computed(() => status.value === 'pending')
const stateSegments = computed(() => ticketStateSegments(metrics.value?.tickets ?? null))
const volumePoints = computed(() => ticketVolumePoints(metrics.value?.tickets ?? null))
const csatDist = computed(() => csatBars(metrics.value?.csat ?? { avg: null, count: 0, distribution: {} }))

const num = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
const num2 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 })
const int = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <header class="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Analytics
        </h1>
        <p class="mt-1 text-sm text-muted">
          Indicadores operacionais por cliente — volume, SLA, CSAT, horas e saldo.
        </p>
      </div>
      <USelect
        v-model="selected"
        :items="options"
        class="w-64"
        :loading="isLoading"
      />
    </header>

    <div v-if="isLoading" class="space-y-3">
      <USkeleton v-for="i in 3" :key="i" class="h-28 w-full rounded-lg" />
    </div>

    <template v-else-if="metrics">
      <div class="mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <UCard :ui="{ body: 'space-y-1' }">
          <p class="text-xs uppercase tracking-wide text-dimmed">CSAT médio</p>
          <p class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
            {{ metrics.csat.avg != null ? num2.format(metrics.csat.avg) : '—' }}
          </p>
          <p class="text-xs text-muted">{{ metrics.csat.count }} avaliações</p>
        </UCard>
        <UCard :ui="{ body: 'space-y-1' }">
          <p class="text-xs uppercase tracking-wide text-dimmed">SLA estourado</p>
          <p
            class="font-display text-3xl font-extrabold tracking-tight"
            :class="(metrics.tickets?.sla_breached ?? 0) > 0 ? 'text-error' : 'text-highlighted'"
          >
            {{ metrics.tickets ? int.format(metrics.tickets.sla_breached) : '—' }}
          </p>
          <p class="text-xs text-muted">
            {{ metrics.tickets ? `${int.format(metrics.tickets.sla_at_risk)} em risco` : 'indisponível' }}
          </p>
        </UCard>
        <UCard :ui="{ body: 'space-y-1' }">
          <p class="text-xs uppercase tracking-wide text-dimmed">Chamados no período</p>
          <p class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
            {{ metrics.tickets ? int.format(metrics.tickets.total) : '—' }}
          </p>
          <p class="text-xs text-muted">últimos {{ metrics.period_days }} dias</p>
        </UCard>
        <UCard :ui="{ body: 'space-y-1' }">
          <p class="text-xs uppercase tracking-wide text-dimmed">Horas lançadas</p>
          <p class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
            {{ num.format(metrics.hours.total_hours) }} h
          </p>
          <p class="text-xs text-muted">{{ metrics.balance.contract_count }} contratos</p>
        </UCard>
      </div>

      <div class="grid gap-4 lg:grid-cols-3">
        <UCard class="lg:col-span-2">
          <p class="mb-3 text-xs uppercase tracking-wide text-dimmed">Volume de chamados por dia</p>
          <AreaChart :points="volumePoints" />
        </UCard>
        <UCard>
          <p class="mb-3 text-xs uppercase tracking-wide text-dimmed">Chamados por estado</p>
          <div class="flex items-center justify-center">
            <DonutChart :segments="stateSegments" palette="semantic" />
          </div>
        </UCard>
        <UCard class="lg:col-span-3">
          <p class="mb-3 text-xs uppercase tracking-wide text-dimmed">Distribuição de CSAT (1–5)</p>
          <BarChart :bars="csatDist" />
        </UCard>
      </div>
    </template>
  </div>
</template>
