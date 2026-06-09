<script setup lang="ts">
import type { Timer } from '~/composables/useTimers'

// Detalhe de um chamado + card de timer proeminente (#1J fase 3). Reaproveita o
// MESMO estado de useTimers da lista (fonte: sidecar), então o timer aqui é o
// mesmo da listagem. Thread de artigos distingue agente x cliente sem cor de marca.
definePageMeta({ middleware: 'admin-auth' })

interface Article {
  From: string
  SenderType: string
  Subject: string
  Body: string
  CreateTime: string
}
interface TicketDetail {
  znuny_ticket_id: number
  ticket_number: string
  title: string
  state: string
  priority: string
  customer_id: string
  owner: string
  created: string
  contract: { code: string, type: string } | null
  articles: Article[]
}

const route = useRoute()
const id = Number(route.params.id)
const headers = useRequestHeaders(['cookie'])

const { data: ticket } = await useAsyncData(`admin-ticket-${id}`, () =>
  $fetch<TicketDetail | null>(`/api/admin/tickets/${id}`, { headers }).catch(() => null))

const {
  timerFor,
  refresh,
  start,
  pause,
  resume,
  useTicker,
} = useTimers()

useTicker()
onMounted(refresh)

const timer = computed<Timer | null>(() => timerFor(id) ?? null)

const busy = ref(false)
async function withBusy(fn: () => Promise<void>) {
  busy.value = true
  try { await fn() }
  finally { busy.value = false }
}

// Diálogo de encerramento.
const stopOpen = ref(false)
function openStop() {
  if (timer.value) stopOpen.value = true
}

// Artigo do agente (atende) vs cliente. Znuny usa SenderType 'agent'/'customer'.
function isAgent(a: Article): boolean {
  return a.SenderType?.toLowerCase() === 'agent'
}

function initials(name: string): string {
  const parts = (name || '?').trim().split(/[\s@.]+/).filter(Boolean)
  return (parts[0]?.[0] ?? '?').toUpperCase() + (parts[1]?.[0]?.toUpperCase() ?? '')
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-5 py-10">
    <ULink to="/atendimento" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para atendimento
    </ULink>

    <!-- 404 -->
    <UCard v-if="!ticket" class="mt-6 text-center">
      <div class="flex flex-col items-center gap-3 py-12">
        <UIcon name="i-lucide-search-x" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Chamado não encontrado
        </p>
        <p class="max-w-sm text-sm text-muted">
          Este chamado pode ter sido encerrado ou o número está incorreto.
        </p>
        <UButton to="/atendimento" variant="soft" color="primary">
          Voltar à lista
        </UButton>
      </div>
    </UCard>

    <template v-else>
      <!-- Cabeçalho -->
      <header class="mt-3 mb-6">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-mono text-sm text-muted">#{{ ticket.ticket_number }}</span>
          <UBadge color="neutral" variant="subtle" size="sm">{{ ticket.state }}</UBadge>
          <UBadge color="neutral" variant="outline" size="sm">{{ ticket.priority }}</UBadge>
        </div>
        <h1 class="mt-1.5 font-display text-2xl font-extrabold tracking-tight text-highlighted">
          {{ ticket.title }}
        </h1>
        <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted">
          <span class="inline-flex items-center gap-1.5">
            <UIcon name="i-lucide-user" class="h-4 w-4" />
            {{ ticket.customer_id }}
          </span>
          <ContractBadge :contract="ticket.contract" />
        </div>
      </header>

      <!-- Card de timer proeminente -->
      <div
        class="mb-8 rounded-2xl border bg-default p-8 transition"
        :class="timer?.status === 'running'
          ? 'border-success/40 shadow-md'
          : timer?.status === 'paused'
            ? 'border-warning/40'
            : 'border-dashed border-muted'"
      >
        <TimerControls
          :znuny-ticket-id="ticket.znuny_ticket_id"
          :timer="timer"
          size="lg"
          :busy="busy"
          @start="withBusy(() => start(ticket!.znuny_ticket_id))"
          @pause="withBusy(() => pause(timer!.id))"
          @resume="withBusy(() => resume(timer!.id))"
          @stop="openStop"
        />
      </div>

      <!-- Thread de artigos -->
      <section>
        <h2 class="mb-4 font-display text-base font-bold text-highlighted">
          Histórico
        </h2>

        <UCard v-if="!ticket.articles || ticket.articles.length === 0" class="text-sm text-muted">
          Nenhuma interação registrada neste chamado.
        </UCard>

        <ol v-else class="space-y-4">
          <li
            v-for="(a, i) in ticket.articles"
            :key="i"
            class="flex gap-3"
            :class="isAgent(a) ? 'flex-row-reverse' : ''"
          >
            <span
              class="mt-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-bold"
              :class="isAgent(a)
                ? 'bg-elevated text-highlighted ring-1 ring-default'
                : 'bg-warning/15 text-warning'"
            >
              {{ initials(a.From) }}
            </span>
            <div
              class="min-w-0 flex-1 rounded-xl border px-4 py-3"
              :class="isAgent(a)
                ? 'border-default bg-elevated/40'
                : 'border-warning/25 bg-warning/5'"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="flex items-center gap-2 text-sm">
                  <span class="font-semibold text-highlighted">{{ a.From }}</span>
                  <UBadge
                    :color="isAgent(a) ? 'neutral' : 'warning'"
                    variant="subtle"
                    size="sm"
                  >
                    {{ isAgent(a) ? 'Atendente' : 'Cliente' }}
                  </UBadge>
                </div>
                <span class="font-mono text-xs text-muted">{{ a.CreateTime }}</span>
              </div>
              <p v-if="a.Subject" class="mt-1 text-sm font-medium text-default">
                {{ a.Subject }}
              </p>
              <p class="mt-1 whitespace-pre-wrap break-words text-sm text-toned">
                {{ a.Body }}
              </p>
            </div>
          </li>
        </ol>
      </section>

      <TimerStopDialog
        v-model:open="stopOpen"
        :timer="timer"
        :ticket-label="`Chamado #${ticket.ticket_number} · ${ticket.title}`"
      />
    </template>
  </div>
</template>
