<script setup lang="ts">
import type { Timer } from '~/composables/useTimers'

// Lista de chamados com timer inline (#1J fase 3). Busca debounced no sidecar,
// timer por linha (idle/running/paused) compartilhando estado via useTimers, e
// diálogo único de "Lançar". Identidade Gerti — cor de marca só na navegação.
definePageMeta({ middleware: 'admin-auth' })

interface TicketRow {
  znuny_ticket_id: number
  ticket_number: string
  title: string
  state: string
  customer_id: string
  owner: string
  created: string
  contract: { code: string, type: string } | null
}

const {
  timers,
  loading: timersLoading,
  activeCount,
  timerFor,
  refresh,
  start,
  pause,
  resume,
  useTicker,
} = useTimers()

// Liga o relógio global (1Hz) e sincroniza os timers ativos no mount.
useTicker()
onMounted(refresh)

// Busca debounced.
const query = ref('')
const debounced = ref('')
let debounceHandle: ReturnType<typeof setTimeout> | null = null
watch(query, (v) => {
  if (debounceHandle) clearTimeout(debounceHandle)
  debounceHandle = setTimeout(() => { debounced.value = v }, 300)
})

const { data: tickets, status, error, refresh: refreshTickets } = await useAsyncData(
  'admin-tickets',
  () => $fetch<TicketRow[] | null>('/api/admin/tickets', {
    query: debounced.value ? { q: debounced.value } : undefined,
  }).then(r => r ?? []),
  { watch: [debounced], default: () => [] as TicketRow[] },
)

const isLoading = computed(() => status.value === 'pending')

// Ação ocupada por ticket (evita duplo clique no botão da linha).
const busyTicket = ref<number | null>(null)
async function withBusy(ticketId: number, fn: () => Promise<void>) {
  busyTicket.value = ticketId
  try { await fn() }
  finally { busyTicket.value = null }
}

// Diálogo de encerramento.
const stopOpen = ref(false)
const stopTimer = ref<Timer | null>(null)
const stopLabel = ref('')
function openStop(row: TicketRow) {
  const t = timerFor(row.znuny_ticket_id)
  if (!t) return
  stopTimer.value = t
  stopLabel.value = `Chamado #${row.ticket_number} · ${row.title}`
  stopOpen.value = true
}

const stateLabel = (s: string) => s || '—'
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <header class="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Atendimento
        </h1>
        <p class="mt-1 text-sm text-muted">
          Cronometre o tempo de cada chamado e lance no contrato do cliente.
        </p>
      </div>
      <div
        class="inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-medium transition"
        :class="activeCount > 0
          ? 'border-success/30 bg-success/10 text-success'
          : 'border-default bg-elevated text-muted'"
      >
        <UIcon name="i-lucide-timer" class="h-4 w-4" />
        {{ activeCount }} {{ activeCount === 1 ? 'timer ativo' : 'timers ativos' }}
        <UIcon v-if="timersLoading" name="i-lucide-loader-circle" class="h-3.5 w-3.5 animate-spin" />
      </div>
    </header>

    <UInput
      v-model="query"
      icon="i-lucide-search"
      size="lg"
      placeholder="Buscar por número, título ou cliente…"
      class="mb-6 w-full"
      :loading="isLoading && !!debounced"
    >
      <template v-if="query" #trailing>
        <UButton color="neutral" variant="link" icon="i-lucide-x" :padded="false" @click="query = ''" />
      </template>
    </UInput>

    <!-- ERRO -->
    <UAlert
      v-if="error"
      color="error"
      variant="soft"
      icon="i-lucide-alert-triangle"
      title="Não foi possível carregar os chamados"
      description="Verifique a conexão com o Znuny e tente novamente."
      class="mb-6"
    >
      <template #actions>
        <UButton color="error" variant="soft" size="sm" @click="refreshTickets()">
          Tentar de novo
        </UButton>
      </template>
    </UAlert>

    <!-- LOADING -->
    <div v-else-if="isLoading" class="space-y-3">
      <USkeleton v-for="i in 5" :key="i" class="h-20 w-full rounded-lg" />
    </div>

    <!-- VAZIO -->
    <UCard v-else-if="!tickets || tickets.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-12">
        <UIcon name="i-lucide-inbox" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">
          {{ debounced ? 'Nenhum chamado encontrado' : 'Nenhum chamado aberto' }}
        </p>
        <p class="max-w-sm text-sm text-muted">
          {{ debounced
            ? 'Ajuste os termos da busca para encontrar o chamado.'
            : 'Quando houver chamados no Znuny, eles aparecerão aqui.' }}
        </p>
      </div>
    </UCard>

    <!-- LISTA -->
    <ul v-else class="space-y-3">
      <li
        v-for="row in tickets"
        :key="row.znuny_ticket_id"
        class="rounded-xl border bg-default px-4 py-4 transition"
        :class="timers[row.znuny_ticket_id]?.status === 'running'
          ? 'border-success/40 shadow-sm'
          : timers[row.znuny_ticket_id]?.status === 'paused'
            ? 'border-warning/40'
            : 'border-default hover:border-muted'"
      >
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="font-mono text-xs text-muted">#{{ row.ticket_number }}</span>
              <UBadge color="neutral" variant="subtle" size="sm">{{ stateLabel(row.state) }}</UBadge>
            </div>
            <NuxtLink
              :to="`/atendimento/${row.znuny_ticket_id}`"
              class="mt-1 block truncate font-display text-base font-bold tracking-tight text-highlighted hover:text-primary"
            >
              {{ row.title }}
            </NuxtLink>
            <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted">
              <span class="inline-flex items-center gap-1">
                <UIcon name="i-lucide-user" class="h-3.5 w-3.5" />
                {{ row.customer_id }}
              </span>
              <ContractBadge :contract="row.contract" />
            </div>
          </div>

          <div class="shrink-0">
            <TimerControls
              :znuny-ticket-id="row.znuny_ticket_id"
              :timer="timers[row.znuny_ticket_id] ?? null"
              size="sm"
              :busy="busyTicket === row.znuny_ticket_id"
              @start="withBusy(row.znuny_ticket_id, () => start(row.znuny_ticket_id))"
              @pause="withBusy(row.znuny_ticket_id, () => pause(timers[row.znuny_ticket_id]!.id))"
              @resume="withBusy(row.znuny_ticket_id, () => resume(timers[row.znuny_ticket_id]!.id))"
              @stop="openStop(row)"
            />
          </div>
        </div>
      </li>
    </ul>

    <TimerStopDialog
      v-model:open="stopOpen"
      :timer="stopTimer"
      :ticket-label="stopLabel"
    />
  </div>
</template>
