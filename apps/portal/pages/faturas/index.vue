<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'
import {
  invoiceStatusColor,
  invoiceStatusLabel,
  moneyBRLFromCents,
} from '~/components/contract/labels'

// #1P — Faturas internas (admin-only; o backend exige require_admin). Read-only:
// listar + baixar o PDF branded. `null` = falha (proxy devolve null em não-200,
// inclui 403 p/ helpdesk). `[]` = vazio.
definePageMeta({ middleware: 'auth' })

interface InvoiceRow {
  number: number
  status: string
  issued_at: string
  due_at: string
  period_start: string
  period_end: string
  currency: string
  total_cents: number
}

const headers = useSidecarHeaders()
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const { data: invoices, pending, refresh } = await useAsyncData('invoices-list', () =>
  $fetch<InvoiceRow[] | null>('/api/portal/invoices', { headers }).catch(() => null))

const loadFailed = computed(() => !pending.value && invoices.value === null)
const isEmpty = computed(() =>
  !pending.value && Array.isArray(invoices.value) && invoices.value.length === 0)

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR')
}
function fmtPeriod(start: string, end: string): string {
  return `${fmtDate(start)} – ${fmtDate(end)}`
}
function padNumber(n: number): string {
  return String(n).padStart(4, '0')
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-5 py-8">
    <header class="mb-8">
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Faturas
      </h1>
      <p class="mt-1 text-sm text-muted">
        Documentos de cobrança do seu contrato. Documento interno — não é nota fiscal.
      </p>
    </header>

    <!-- Loading -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 4" :key="n" class="h-[72px] animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-4 py-10">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-error/10 text-error">
          <UIcon name="i-lucide-cloud-off" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar as faturas</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            As faturas estão indisponíveis no momento. Tente novamente em instantes.
          </p>
        </div>
        <UButton color="neutral" variant="subtle" icon="i-lucide-rotate-cw" label="Tentar novamente" @click="refresh()" />
      </div>
    </UCard>

    <!-- Vazio -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-4 py-12">
        <span
          class="inline-flex h-16 w-16 items-center justify-center rounded-2xl text-white shadow-sm"
          :style="{ background: 'linear-gradient(135deg, var(--brand-primary), var(--brand-accent))' }"
        >
          <UIcon name="i-lucide-receipt" class="h-8 w-8" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Nenhuma fatura emitida</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            Quando uma fatura for gerada para o seu contrato, ela aparecerá aqui para download.
          </p>
        </div>
      </div>
    </UCard>

    <!-- Lista -->
    <ul v-else class="space-y-3">
      <li v-for="inv in invoices ?? []" :key="inv.number">
        <div class="rounded-xl border border-default bg-default px-4 py-3.5">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-sm font-semibold text-highlighted">
                  Fatura #{{ padNumber(inv.number) }}
                </span>
                <UBadge :color="invoiceStatusColor(inv.status)" variant="soft" size="sm">
                  {{ invoiceStatusLabel(inv.status) }}
                </UBadge>
              </div>
              <p class="mt-1 text-sm text-muted">
                Período {{ fmtPeriod(inv.period_start, inv.period_end) }} · Vence {{ fmtDate(inv.due_at) }}
              </p>
            </div>
            <div class="flex flex-col items-end gap-2">
              <span class="font-display text-lg font-bold text-highlighted">
                {{ moneyBRLFromCents(inv.total_cents) }}
              </span>
              <a
                :href="`/api/portal/invoices/${inv.number}/pdf`"
                target="_blank"
                rel="noopener"
                class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-sm font-medium text-[var(--brand-primary)] transition hover:bg-[color-mix(in_srgb,var(--brand-primary)_12%,transparent)]"
              >
                <UIcon name="i-lucide-download" class="h-4 w-4" />
                Baixar PDF
              </a>
            </div>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
