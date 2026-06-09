<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

// #1E fase 3 — Detalhe do chamado + responder. SSR. Em 404 NÃO vazamos
// existência: mostramos "chamado não encontrado" genérico. Guarda anti-IDOR
// fica no backend (o sidecar valida posse e responde 404). H8: distinção
// visual cliente/agente por tokens semânticos, nunca pela cor da marca.
definePageMeta({ middleware: 'auth' })

interface Article {
  From?: string
  SenderType?: string
  Subject?: string
  Body?: string
  CreateTime?: string
}
interface CsatState {
  submitted: boolean
  score?: number
  eligible?: boolean
}
interface TicketDetail {
  znuny_ticket_id: number
  ticket_number: string
  title: string
  state: string
  priority: string
  created: string
  contract_id: string | null
  articles: Article[]
  csat?: CsatState
}
interface SelectableContract { id: string, code: string }

const route = useRoute()
const id = computed(() => String(route.params.id))
const headers = useRequestHeaders(['cookie'])
const toast = useToast()
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const { data: ticket, pending, refresh } = await useAsyncData(`ticket-${id.value}`, () =>
  $fetch<TicketDetail | null>(`/api/portal/tickets/${id.value}`, { headers }).catch(() => null))

const { data: contracts } = await useAsyncData('ticket-detail-contracts', () =>
  $fetch<SelectableContract[]>('/api/portal/ticketing/contracts', { headers })
    .catch(() => [] as SelectableContract[]))
const contractLabel = computed(() => {
  const cid = ticket.value?.contract_id
  if (!cid) return null
  const found = (contracts.value ?? []).find(c => c.id === cid)
  return found?.code ?? 'Contrato vinculado'
})

const notFound = computed(() => !pending.value && !ticket.value)

// Ordena os artigos cronologicamente (defensivo: CreateTime pode faltar).
const thread = computed<Article[]>(() => {
  const list = [...(ticket.value?.articles ?? [])]
  return list.sort((a, b) => new Date(a.CreateTime ?? 0).getTime() - new Date(b.CreateTime ?? 0).getTime())
})
function isAgent(a: Article): boolean {
  const s = (a.SenderType ?? '').toLowerCase()
  return s === 'agent' || s === 'system'
}

type BadgeColor = 'success' | 'warning' | 'error' | 'info' | 'neutral'
function stateColor(state: string): BadgeColor {
  const s = state.toLowerCase()
  if (/(fech|resolv|closed|resolved)/.test(s)) return 'success'
  if (/(aguard|pend|pending|wait)/.test(s)) return 'warning'
  if (/(novo|aberto|open|new)/.test(s)) return 'info'
  return 'neutral'
}

function fmtDate(iso: string | undefined | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}
function fmtDateTime(iso: string | undefined | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// --- Responder ---
const replyBody = ref('')
const replying = ref(false)
const replyError = ref('')

async function sendReply() {
  replyError.value = ''
  if (!replyBody.value.trim()) {
    replyError.value = 'Escreva uma mensagem antes de enviar.'
    return
  }
  replying.value = true
  try {
    await $fetch(`/api/portal/tickets/${id.value}/reply`, {
      method: 'POST',
      body: { body: replyBody.value.trim() },
    })
    replyBody.value = ''
    await refresh()
    toast.add({
      title: 'Resposta enviada',
      description: 'Sua mensagem foi adicionada ao chamado.',
      color: 'success',
      icon: 'i-lucide-check-circle',
    })
  }
  catch (err: unknown) {
    const e = err as { status?: number, statusCode?: number }
    const status = e.status ?? e.statusCode
    if (status === 404) {
      replyError.value = 'Este chamado não está mais disponível. Atualize a página.'
    }
    else if (status === 503) {
      replyError.value = 'O sistema de chamados está indisponível. Tente novamente em instantes.'
    }
    else {
      replyError.value = 'Não foi possível enviar sua resposta. Tente novamente.'
    }
  }
  finally {
    replying.value = false
  }
}

// --- CSAT (#1M) ---
// Mostra o widget quando o ticket está fechado e ainda não foi avaliado
// (ticket.csat.eligible). Em sucesso, troca para o estado "respondido" local
// (sem precisar de refresh) e atualiza o bloco csat do ticket.
const csatSubmitting = ref(false)
const csatShowPrompt = computed(() => ticket.value?.csat?.eligible === true)
const csatSubmittedScore = computed<number | null>(() =>
  ticket.value?.csat?.submitted ? (ticket.value.csat.score ?? null) : null)

async function sendCsat(payload: { score: number, comment: string }) {
  csatSubmitting.value = true
  try {
    await $fetch(`/api/portal/tickets/${id.value}/csat`, {
      method: 'POST',
      body: { score: payload.score, comment: payload.comment || null },
    })
    if (ticket.value) {
      ticket.value.csat = { submitted: true, score: payload.score }
    }
    toast.add({
      title: 'Avaliação enviada',
      description: 'Obrigado pelo seu feedback!',
      color: 'success',
      icon: 'i-lucide-check-circle',
    })
  }
  catch (err: unknown) {
    const e = err as { status?: number, statusCode?: number }
    const status = e.status ?? e.statusCode
    if (status === 409) {
      // já avaliado em outra aba/sessão — sincroniza o estado e avisa suave.
      if (ticket.value) ticket.value.csat = { submitted: true, score: payload.score }
      toast.add({
        title: 'Chamado já avaliado',
        description: 'Este chamado já tinha uma avaliação registrada.',
        color: 'warning',
        icon: 'i-lucide-info',
      })
    }
    else if (status === 422) {
      toast.add({
        title: 'Avaliação indisponível',
        description: 'Só é possível avaliar chamados já encerrados.',
        color: 'warning',
        icon: 'i-lucide-alert-circle',
      })
    }
    else {
      toast.add({
        title: 'Não foi possível avaliar',
        description: 'Tente novamente em instantes.',
        color: 'error',
        icon: 'i-lucide-alert-circle',
      })
    }
  }
  finally {
    csatSubmitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-8">
    <NuxtLink
      to="/tickets"
      class="mb-6 inline-flex items-center gap-1.5 text-sm text-muted transition hover:text-highlighted"
    >
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" /> Voltar para chamados
    </NuxtLink>

    <!-- Loading -->
    <div v-if="pending" class="space-y-4">
      <div class="h-24 animate-pulse rounded-xl border border-default bg-elevated" />
      <div class="h-40 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Não encontrado (não vaza existência) -->
    <UCard v-else-if="notFound" class="text-center">
      <div class="flex flex-col items-center gap-4 py-12">
        <span class="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-elevated text-dimmed">
          <UIcon name="i-lucide-search-x" class="h-7 w-7" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Chamado não encontrado</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            Este chamado não existe ou não está disponível para a sua conta.
          </p>
        </div>
        <UButton to="/tickets" color="neutral" variant="subtle" icon="i-lucide-arrow-left" label="Ver meus chamados" />
      </div>
    </UCard>

    <template v-else-if="ticket">
      <!-- Cabeçalho -->
      <header class="mb-6">
        <p class="text-sm text-muted">{{ tenantName }} · Chamado #{{ ticket.ticket_number }}</p>
        <h1 class="mt-1 font-display text-2xl font-extrabold tracking-tight text-highlighted">
          {{ ticket.title || 'Sem assunto' }}
        </h1>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <UBadge :color="stateColor(ticket.state)" variant="soft">{{ ticket.state }}</UBadge>
          <UBadge v-if="ticket.priority" color="neutral" variant="subtle">
            <UIcon name="i-lucide-flag" class="mr-1 h-3 w-3" />{{ ticket.priority }}
          </UBadge>
          <span v-if="contractLabel" class="inline-flex items-center gap-1.5 text-xs text-muted">
            <UIcon name="i-lucide-file-text" class="h-3.5 w-3.5" />{{ contractLabel }}
          </span>
          <span class="inline-flex items-center gap-1.5 text-xs text-muted">
            <UIcon name="i-lucide-calendar" class="h-3.5 w-3.5" />Aberto em {{ fmtDate(ticket.created) }}
          </span>
        </div>
      </header>

      <!-- CSAT (#1M): avaliação inline quando o chamado está fechado.
           H8: cores semânticas no widget, nunca a marca. -->
      <section
        v-if="csatShowPrompt || csatSubmittedScore != null"
        class="mb-6"
        aria-label="Avaliação do atendimento"
      >
        <CsatPrompt
          :submitted-score="csatSubmittedScore"
          :loading="csatSubmitting"
          @submit="sendCsat"
        />
      </section>

      <!-- Thread -->
      <section class="space-y-4" aria-label="Histórico de mensagens">
        <article
          v-for="(a, idx) in thread"
          :key="idx"
          class="rounded-xl border px-4 py-3.5"
          :class="isAgent(a)
            ? 'border-info/30 bg-info/5'
            : 'border-default bg-elevated'"
        >
          <div class="mb-2 flex flex-wrap items-center gap-2">
            <span
              class="inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold"
              :class="isAgent(a) ? 'bg-info/15 text-info' : 'bg-default text-toned'"
              aria-hidden="true"
            >
              <UIcon :name="isAgent(a) ? 'i-lucide-headset' : 'i-lucide-user'" class="h-3.5 w-3.5" />
            </span>
            <span class="text-sm font-medium text-highlighted">{{ a.From || (isAgent(a) ? 'Suporte' : 'Você') }}</span>
            <UBadge :color="isAgent(a) ? 'info' : 'neutral'" variant="subtle" size="sm">
              {{ isAgent(a) ? 'Suporte' : 'Cliente' }}
            </UBadge>
            <span class="ml-auto text-xs text-dimmed">{{ fmtDateTime(a.CreateTime) }}</span>
          </div>
          <p v-if="a.Subject && a.Subject !== ticket.title" class="mb-1 text-sm font-medium text-toned">
            {{ a.Subject }}
          </p>
          <p class="whitespace-pre-wrap break-words text-sm leading-relaxed text-toned">{{ a.Body }}</p>
        </article>

        <p v-if="!thread.length" class="rounded-xl border border-default bg-elevated px-4 py-6 text-center text-sm text-muted">
          Este chamado ainda não tem mensagens.
        </p>
      </section>

      <!-- Responder -->
      <section class="mt-6" aria-label="Responder ao chamado">
        <UCard>
          <h2 class="mb-3 font-display text-sm font-semibold text-toned">Responder</h2>
          <UTextarea
            v-model="replyBody"
            :rows="4"
            placeholder="Escreva sua resposta…"
            size="lg"
            class="w-full"
            :disabled="replying"
            aria-label="Sua resposta"
          />
          <UAlert
            v-if="replyError"
            class="mt-3"
            color="error"
            variant="soft"
            icon="i-lucide-alert-circle"
            :title="replyError"
          />
          <div class="mt-4 flex justify-end">
            <UButton
              color="primary"
              size="lg"
              icon="i-lucide-send"
              :loading="replying"
              :disabled="replying || !replyBody.trim()"
              label="Enviar resposta"
              @click="sendReply"
            />
          </div>
        </UCard>
      </section>
    </template>
  </div>
</template>
