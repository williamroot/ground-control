<script setup lang="ts">
import { invoiceStatusColor, invoiceStatusLabel, moneyBRLFromCents } from '#shared/contracts'

// #1P — Gestão de faturas internas no console (agente Gerti). Lista as faturas
// do cliente, gera uma a partir de um ciclo (cycle_id), marca paga / cancela.
// O backend (require admin session) escopa por tenant e aplica as transições.
definePageMeta({ middleware: 'admin-auth' })

const route = useRoute()
const tenantId = route.params.id as string
const headers = useRequestHeaders(['cookie'])
const toast = useToast()

interface InvoiceRow {
  id: string
  number: number
  status: string
  issued_at: string
  due_at: string
  period_start: string
  period_end: string
  currency: string
  subtotal_cents: number
  total_cents: number
}

const { data: invoices, refresh, pending } = await useAsyncData(`admin-invoices-${tenantId}`, () =>
  $fetch<InvoiceRow[] | null>(`/api/admin/tenants/${tenantId}/invoices`, { headers }).catch(() => null))

const cycleId = ref('')
const generating = ref(false)

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR')
}
function isTerminal(status: string): boolean {
  return status === 'paid' || status === 'void'
}

async function generate() {
  if (!cycleId.value.trim()) {
    toast.add({ title: 'Informe o ID do ciclo', color: 'warning' })
    return
  }
  generating.value = true
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/invoices`, {
      method: 'POST',
      body: { cycle_id: cycleId.value.trim() },
    })
    cycleId.value = ''
    toast.add({ title: 'Fatura gerada', color: 'success' })
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    const msg
      = err.statusCode === 409
        ? 'Este ciclo já possui fatura ou ainda está aberto.'
        : err.statusCode === 404
          ? 'Ciclo não encontrado para este cliente.'
          : err.data?.detail || 'Falha ao gerar a fatura.'
    toast.add({ title: 'Não foi possível gerar', description: msg, color: 'error' })
  }
  finally {
    generating.value = false
  }
}

async function markPaid(inv: InvoiceRow) {
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/invoices/${inv.number}/paid`, { method: 'POST' })
    toast.add({ title: `Fatura #${inv.number} marcada como paga`, color: 'success' })
    await refresh()
  }
  catch {
    toast.add({ title: 'Falha ao marcar como paga', color: 'error' })
  }
}

async function markVoid(inv: InvoiceRow) {
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/invoices/${inv.number}/void`, { method: 'POST' })
    toast.add({ title: `Fatura #${inv.number} cancelada`, color: 'neutral' })
    await refresh()
  }
  catch {
    toast.add({ title: 'Falha ao cancelar', color: 'error' })
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <ULink :to="`/clientes/${tenantId}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <header class="mt-3 mb-6">
      <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
        Faturas
      </h1>
      <p class="mt-1 text-sm text-muted">
        Gere faturas a partir de ciclos fechados e gerencie o status. Documento interno — não é nota fiscal.
      </p>
    </header>

    <!-- Gerar do ciclo -->
    <UCard class="mb-6">
      <div class="flex flex-wrap items-end gap-3">
        <UFormField label="ID do ciclo (cycle_id)" class="flex-1 min-w-[260px]">
          <UInput v-model="cycleId" placeholder="uuid do ciclo fechado" class="w-full" />
        </UFormField>
        <UButton
          icon="i-lucide-file-plus"
          :loading="generating"
          label="Gerar do ciclo"
          @click="generate"
        />
      </div>
    </UCard>

    <!-- Lista -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 3" :key="n" class="h-16 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <UCard v-else-if="!invoices || invoices.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-receipt" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nenhuma fatura ainda</p>
        <p class="text-sm text-muted">Gere a primeira a partir de um ciclo fechado acima.</p>
      </div>
    </UCard>

    <div v-else class="overflow-hidden rounded-xl border border-default">
      <table class="w-full text-sm">
        <thead class="bg-elevated text-left text-xs uppercase text-muted">
          <tr>
            <th class="px-4 py-2.5">Número</th>
            <th class="px-4 py-2.5">Período</th>
            <th class="px-4 py-2.5">Vencimento</th>
            <th class="px-4 py-2.5 text-right">Total</th>
            <th class="px-4 py-2.5">Status</th>
            <th class="px-4 py-2.5 text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="inv in invoices" :key="inv.id" class="border-t border-default">
            <td class="px-4 py-3 font-mono font-semibold text-highlighted">
              #{{ String(inv.number).padStart(4, '0') }}
            </td>
            <td class="px-4 py-3 text-muted">
              {{ fmtDate(inv.period_start) }} – {{ fmtDate(inv.period_end) }}
            </td>
            <td class="px-4 py-3 text-muted">{{ fmtDate(inv.due_at) }}</td>
            <td class="px-4 py-3 text-right font-semibold text-highlighted">
              {{ moneyBRLFromCents(inv.total_cents) }}
            </td>
            <td class="px-4 py-3">
              <UBadge :color="invoiceStatusColor(inv.status)" variant="soft" size="sm">
                {{ invoiceStatusLabel(inv.status) }}
              </UBadge>
            </td>
            <td class="px-4 py-3">
              <div class="flex justify-end gap-2">
                <UButton
                  v-if="!isTerminal(inv.status)"
                  size="xs"
                  color="success"
                  variant="soft"
                  icon="i-lucide-check"
                  label="Marcar paga"
                  @click="markPaid(inv)"
                />
                <UButton
                  v-if="!isTerminal(inv.status)"
                  size="xs"
                  color="neutral"
                  variant="soft"
                  icon="i-lucide-ban"
                  label="Cancelar"
                  @click="markVoid(inv)"
                />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
