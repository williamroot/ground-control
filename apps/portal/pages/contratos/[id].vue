<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'
import { glosaMeta } from '~/components/contract/glosa'
import { statusColor, statusLabel, typeLabel } from '~/components/contract/labels'

definePageMeta({ middleware: 'auth' }) // #1H: sessão + papel admin

interface Saldo { kind: string, remaining: number | null }
interface Cycle {
  id: string, kind: string, period_start: string, period_end: string
  status: string, closed_at: string | null, totals: Record<string, number> | null
}
interface Detail {
  id: string, code: string, type: string, status: string, starts_on: string, ends_on: string
  initial_hours: number | null, initial_amount_brl: number | null, initial_service_count: number | null
  unit_price_brl: number | null, saldo: Saldo, consumed_percent: number | null
  cycles: Cycle[]
  adjustment_rule: { index_code: string, cadence_months: number, next_run_on: string, cap_percent: number | null, last_applied_on: string | null, last_applied_percent: number | null } | null
  renewal_policy: { auto_renew: boolean, notice_days: number, next_review_on: string, renewal_term_months: number | null } | null
  billing_parties: { legal_name: string, document: string, fiscal_address: Record<string, unknown>, payment_method: string | null }[]
}
interface SeriesPoint { bucket: string, value: number }
interface Series { granularity: string, kind: string, points: SeriesPoint[] }
interface CItem {
  id: number, occurred_at: string, source_kind: string, source_ref: string
  billable_minutes: number, billable_amount_brl: number
  glosa: { status: 'pending' | 'approved' | 'rejected' } | null, counts_toward_balance: boolean
}
interface CPage { page: number, page_size: number, total: number, items: CItem[] }

const route = useRoute()
const id = computed(() => String(route.params.id))
const headers = useRequestHeaders(['cookie'])

// Auth + papel admin garantidos pela guarda global (middleware/auth.global.ts, #1H).
const { data: detail, error } = await useAsyncData(`detail-${id.value}`, () =>
  $fetch<Detail>(`/api/portal/contracts/${id.value}`, { headers }).catch(() => null))
const { data: series } = await useAsyncData(`series-${id.value}`, () =>
  $fetch<Series>(`/api/portal/contracts/${id.value}/series`, { headers }).catch(() => null))

const page = ref(1)
const { data: ledger } = await useAsyncData(`ledger-${id.value}`, () =>
  $fetch<CPage>(`/api/portal/contracts/${id.value}/consumption?page=${page.value}&page_size=50`, { headers })
    .catch(() => null), { watch: [page] })

// Mantém o estado de branding hidratado pelo layout (SSR, sem flash); não consumido aqui.
const _branding = useState<Branding>('branding', () => DEFAULT_BRANDING)

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const num = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}
function saldoBig(d: Detail): string {
  const r = d.saldo?.remaining; const k = d.saldo?.kind
  if (r == null) return '—'
  if (k === 'hours') return `${num.format(r)} h`
  if (k === 'brl') return brl.format(r)
  if (k === 'services') return `${num.format(r)} serviços`
  return num.format(r)
}
const overage = computed(() => {
  const d = detail.value
  return !!d && d.saldo?.remaining != null && d.saldo.remaining < 0
})
const CYCLE_STATUS: Record<string, { label: string, color: 'success' | 'warning' | 'neutral' }> = {
  open: { label: 'Aberto', color: 'warning' }, closed: { label: 'Fechado', color: 'success' },
  invoiced: { label: 'Faturado', color: 'neutral' },
}
function totalPages(p: CPage | null): number {
  if (!p) return 1
  return Math.max(1, Math.ceil(p.total / p.page_size))
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-8">
    <NuxtLink to="/" class="mb-6 inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" /> Voltar
    </NuxtLink>

    <div v-if="error || !detail" class="rounded-xl border border-neutral-200 p-8 text-center text-neutral-500">
      Não foi possível carregar este contrato.
    </div>

    <template v-else>
      <header class="mb-6 flex flex-wrap items-center gap-3">
        <h1 class="font-display text-2xl font-extrabold tracking-tight text-neutral-900">{{ detail.code }}</h1>
        <UBadge color="primary" variant="subtle">{{ typeLabel(detail.type) }}</UBadge>
        <UBadge :color="statusColor(detail.status)" variant="soft">{{ statusLabel(detail.status) }}</UBadge>
        <span class="ml-auto text-sm text-neutral-500">{{ fmtDate(detail.starts_on) }} — {{ fmtDate(detail.ends_on) }}</span>
      </header>

      <!-- Hero saldo -->
      <UCard class="mb-6">
        <p class="text-xs uppercase tracking-wide text-neutral-400">Saldo atual</p>
        <p class="font-display text-4xl font-extrabold tracking-tight text-neutral-900">{{ saldoBig(detail) }}</p>
        <ProgressBar v-if="detail.consumed_percent != null" class="mt-4" :percent="detail.consumed_percent" :overage="overage" />
        <p v-if="overage" class="mt-2 text-sm font-semibold text-red-700">Franquia excedida (overage)</p>
      </UCard>

      <!-- Série de consumo -->
      <UCard v-if="series && series.kind !== 'n/a'" class="mb-6">
        <p class="mb-3 font-display text-sm font-semibold text-neutral-700">Consumo ao longo do tempo</p>
        <AreaChart :points="series.points" />
      </UCard>

      <!-- Timeline de ciclos -->
      <UCard v-if="detail.cycles.length" class="mb-6">
        <p class="mb-3 font-display text-sm font-semibold text-neutral-700">Ciclos</p>
        <div class="space-y-2">
          <div v-for="cy in detail.cycles" :key="cy.id" class="flex flex-wrap items-center gap-3 rounded-lg border border-neutral-100 px-3 py-2">
            <UBadge :color="(CYCLE_STATUS[cy.status] ?? { color: 'neutral' }).color" variant="soft" size="sm">
              {{ (CYCLE_STATUS[cy.status] ?? { label: cy.status }).label }}
            </UBadge>
            <span class="text-sm text-neutral-600">{{ cy.kind }}</span>
            <span class="text-sm text-neutral-500">{{ fmtDate(cy.period_start) }} — {{ fmtDate(cy.period_end) }}</span>
            <span v-if="cy.totals" class="ml-auto text-xs text-neutral-500">
              Consumido {{ num.format((cy.totals.consumed_minutes ?? 0) / 60) }} h ·
              Overage {{ brl.format(cy.totals.overage_amount_brl ?? 0) }}
            </span>
          </div>
        </div>
      </UCard>

      <!-- Extrato paginado -->
      <UCard v-if="ledger" class="mb-6">
        <div class="mb-3 flex items-center justify-between">
          <p class="font-display text-sm font-semibold text-neutral-700">Extrato de consumo</p>
          <span class="text-xs text-neutral-400">{{ ledger.total }} lançamentos</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="text-left text-xs uppercase tracking-wide text-neutral-400">
              <tr><th class="py-2">Data</th><th>Origem</th><th class="text-right">Min</th><th class="text-right pr-4">R$</th><th class="pl-4">Glosa</th></tr>
            </thead>
            <tbody>
              <tr v-for="it in ledger.items" :key="it.id" class="border-t border-neutral-100"
                :class="!it.counts_toward_balance ? 'opacity-60' : ''">
                <td class="py-2 text-neutral-600">{{ fmtDate(it.occurred_at) }}</td>
                <td class="text-neutral-600">{{ it.source_kind }} · {{ it.source_ref }}</td>
                <td class="text-right text-neutral-600" :class="it.glosa?.status === 'approved' ? 'line-through' : ''">{{ num.format(it.billable_minutes) }}</td>
                <td class="text-right text-neutral-600 pr-4" :class="it.glosa?.status === 'approved' ? 'line-through' : ''">{{ brl.format(it.billable_amount_brl) }}</td>
                <td class="pl-4">
                  <span v-if="glosaMeta(it.glosa?.status ?? null)" class="text-xs font-medium" :class="glosaMeta(it.glosa?.status ?? null)!.classes">
                    {{ glosaMeta(it.glosa?.status ?? null)!.label }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="totalPages(ledger) > 1" class="mt-4 flex items-center justify-center gap-3">
          <UButton size="sm" variant="ghost" color="neutral" :disabled="page <= 1" icon="i-lucide-chevron-left" @click="page = Math.max(1, page - 1)" />
          <span class="text-sm text-neutral-500">{{ page }} / {{ totalPages(ledger) }}</span>
          <UButton size="sm" variant="ghost" color="neutral" :disabled="page >= totalPages(ledger)" icon="i-lucide-chevron-right" @click="page = page + 1" />
        </div>
      </UCard>

      <div class="grid gap-6 md:grid-cols-2">
        <!-- Reajuste & renovação -->
        <UCard v-if="detail.adjustment_rule || detail.renewal_policy">
          <p class="mb-3 font-display text-sm font-semibold text-neutral-700">Reajuste & renovação</p>
          <dl class="space-y-1.5 text-sm">
            <template v-if="detail.adjustment_rule">
              <div class="flex justify-between"><dt class="text-neutral-500">Índice</dt><dd>{{ detail.adjustment_rule.index_code }}</dd></div>
              <div class="flex justify-between"><dt class="text-neutral-500">Cadência</dt><dd>{{ detail.adjustment_rule.cadence_months }} meses</dd></div>
              <div class="flex justify-between"><dt class="text-neutral-500">Teto</dt><dd>{{ detail.adjustment_rule.cap_percent != null ? `${detail.adjustment_rule.cap_percent}%` : '—' }}</dd></div>
              <div class="flex justify-between"><dt class="text-neutral-500">Próximo reajuste</dt><dd>{{ fmtDate(detail.adjustment_rule.next_run_on) }}</dd></div>
            </template>
            <template v-if="detail.renewal_policy">
              <div class="flex justify-between"><dt class="text-neutral-500">Auto-renovação</dt><dd>{{ detail.renewal_policy.auto_renew ? 'Sim' : 'Não' }}</dd></div>
              <div class="flex justify-between"><dt class="text-neutral-500">Aviso prévio</dt><dd>{{ detail.renewal_policy.notice_days }} dias</dd></div>
              <div class="flex justify-between"><dt class="text-neutral-500">Próxima revisão</dt><dd>{{ fmtDate(detail.renewal_policy.next_review_on) }}</dd></div>
            </template>
          </dl>
        </UCard>

        <!-- Partes de faturamento -->
        <UCard v-if="detail.billing_parties.length">
          <p class="mb-3 font-display text-sm font-semibold text-neutral-700">Partes de faturamento</p>
          <div v-for="p in detail.billing_parties" :key="p.document" class="space-y-0.5 text-sm">
            <p class="font-medium text-neutral-800">{{ p.legal_name }}</p>
            <p class="text-neutral-500">{{ p.document }}</p>
            <p v-if="p.payment_method" class="text-neutral-500">Pagamento: {{ p.payment_method }}</p>
          </div>
        </UCard>
      </div>
    </template>
  </div>
</template>
