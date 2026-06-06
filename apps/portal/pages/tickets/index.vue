<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

// #1E fase 3 — Lista de chamados (substitui o placeholder). O backend já escopa
// por papel (#1H): helpdesk vê os próprios; admin vê os da empresa. Aqui só
// renderizamos. Estados explícitos: loading, vazio (CTA), erro (sidecar 503).
definePageMeta({ middleware: 'auth' })

interface TicketRow {
  znuny_ticket_id: number
  ticket_number: string
  title: string
  state: string
  created: string
  contract_id: string | null
}
interface SelectableContract { id: string, code: string }

const headers = useRequestHeaders(['cookie'])
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')
const { data: me } = await useMe()

// `null` = falha (proxy devolve null em não-200) → estado de erro. `[]` = vazio.
const { data: tickets, pending, refresh } = await useAsyncData('tickets-list', () =>
  $fetch<TicketRow[] | null>('/api/portal/tickets', { headers }).catch(() => null))

// Resolve o código do contrato a partir do catálogo selecionável (best-effort).
const { data: contracts } = await useAsyncData('tickets-contracts', () =>
  $fetch<SelectableContract[]>('/api/portal/ticketing/contracts', { headers })
    .catch(() => [] as SelectableContract[]))
const contractCode = computed(() => {
  const map = new Map<string, string>()
  for (const c of contracts.value ?? []) map.set(c.id, c.code)
  return map
})
function contractLabel(id: string | null): string {
  if (!id) return 'Sem contrato'
  return contractCode.value.get(id) ?? 'Vinculado'
}

const loadFailed = computed(() => !pending.value && tickets.value === null)
const isEmpty = computed(() => !pending.value && Array.isArray(tickets.value) && tickets.value.length === 0)

// Cor do badge de estado: tokens semânticos do Nuxt UI (NUNCA a cor da marca, H8).
type BadgeColor = 'success' | 'warning' | 'error' | 'info' | 'neutral'
function stateColor(state: string): BadgeColor {
  const s = state.toLowerCase()
  if (/(fech|resolv|closed|resolved)/.test(s)) return 'success'
  if (/(aguard|pend|pending|wait)/.test(s)) return 'warning'
  if (/(novo|aberto|open|new)/.test(s)) return 'info'
  return 'neutral'
}

function fmtDate(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-5 py-8">
    <header class="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-sm text-muted">{{ tenantName }}</p>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Chamados
        </h1>
        <p class="mt-1 text-sm text-muted">
          {{ me?.role === 'admin'
            ? 'Acompanhe os chamados de suporte da sua empresa.'
            : 'Acompanhe seus chamados de suporte.' }}
        </p>
      </div>
      <UButton to="/tickets/novo" color="primary" size="lg" icon="i-lucide-plus" label="Novo chamado" />
    </header>

    <!-- Loading -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 3" :key="n" class="h-[72px] animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro (sidecar indisponível) -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-4 py-10">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-error/10 text-error">
          <UIcon name="i-lucide-cloud-off" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar os chamados</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            O sistema de chamados está indisponível no momento. Tente novamente em instantes.
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
          <UIcon name="i-lucide-ticket" class="h-8 w-8" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Você ainda não abriu chamados</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            Precisa de ajuda do suporte? Abra um chamado e acompanhe a resposta por aqui.
          </p>
        </div>
        <UButton to="/tickets/novo" color="primary" size="lg" icon="i-lucide-plus" label="Abrir primeiro chamado" />
      </div>
    </UCard>

    <!-- Lista -->
    <ul v-else class="space-y-3">
      <li v-for="t in tickets ?? []" :key="t.znuny_ticket_id">
        <NuxtLink
          :to="`/tickets/${t.znuny_ticket_id}`"
          class="block rounded-xl border border-default bg-default px-4 py-3.5 transition hover:border-highlighted hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-mono text-xs text-dimmed">#{{ t.ticket_number }}</span>
                <UBadge :color="stateColor(t.state)" variant="soft" size="sm">{{ t.state }}</UBadge>
              </div>
              <p class="mt-1 truncate font-medium text-highlighted">{{ t.title || 'Sem assunto' }}</p>
            </div>
            <UIcon name="i-lucide-chevron-right" class="mt-1 h-5 w-5 shrink-0 text-dimmed" />
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
            <span class="inline-flex items-center gap-1.5">
              <UIcon name="i-lucide-file-text" class="h-3.5 w-3.5" />
              {{ contractLabel(t.contract_id) }}
            </span>
            <span class="inline-flex items-center gap-1.5">
              <UIcon name="i-lucide-calendar" class="h-3.5 w-3.5" />
              {{ fmtDate(t.created) }}
            </span>
          </div>
        </NuxtLink>
      </li>
    </ul>
  </div>
</template>
