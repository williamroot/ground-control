<script setup lang="ts">
import type { Approval, Decision } from '~/composables/useApprovals'
import { decisionError, statusColor, statusLabel, validateDecision } from '~/composables/useApprovals'

// R7 — fila de aprovação do cliente.
//
// *"Todo ticket passa, quando essa chave tá habilitada, todo ticket passa por
// aqui e vai pra um aprovador."* (07:40)
//
// O chamado listado aqui está em estado REAL de espera no Znuny — não foi
// criado e escondido. Enquanto ninguém decide, nenhum agente o atende.
definePageMeta({ middleware: 'auth' })

const headers = useSidecarHeaders()
const toast = useToast()

const { data: approvals, refresh, pending } = await useAsyncData('approvals', () =>
  $fetch<Approval[] | null>('/api/portal/approvals', { headers }).catch(() => null))

const open = ref<number | null>(null)
const decision = ref<Decision>('approved')
const reason = ref('')
const saving = ref(false)

const errors = computed(() => validateDecision(decision.value, reason.value))

function start(ticketId: number, d: Decision) {
  open.value = ticketId
  decision.value = d
  reason.value = ''
}

function fmt(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR')
}

async function submit(ticketId: number) {
  if (errors.value.length) return
  saving.value = true
  try {
    await $fetch(`/api/portal/tickets/${ticketId}/approval`, {
      method: 'POST',
      body: { decision: decision.value, reason: reason.value.trim() || null },
    })
    toast.add({
      title: decision.value === 'approved' ? 'Pedido aprovado' : 'Pedido reprovado',
      color: decision.value === 'approved' ? 'success' : 'neutral',
    })
    open.value = null
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    toast.add({
      title: 'Não foi possível decidir',
      description: decisionError(err.statusCode, err.data?.detail),
      color: 'error',
    })
    // 409 significa que outra pessoa já decidiu: a lista precisa refletir isso.
    if (err.statusCode === 409) await refresh()
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-10">
    <header class="mb-6">
      <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
        Aprovações
      </h1>
      <p class="mt-1 text-sm text-muted">
        Pedidos aguardando sua decisão. Enquanto não forem aprovados, nenhum atendimento começa.
      </p>
    </header>

    <div v-if="pending" class="space-y-3">
      <div v-for="n in 2" :key="n" class="h-24 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <UCard v-else-if="!approvals || approvals.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-check-circle-2" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nada aguardando você</p>
        <p class="text-sm text-muted">Novos pedidos aparecem aqui assim que forem abertos.</p>
      </div>
    </UCard>

    <div v-else class="space-y-4">
      <UCard v-for="a in approvals" :key="a.id">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="font-semibold text-highlighted">
              Chamado #{{ a.znuny_ticket_id }}
            </p>
            <p class="text-sm text-muted">
              Aberto por {{ a.requested_by }} em {{ fmt(a.created_at) }}
            </p>
          </div>
          <UBadge :color="statusColor(a.status)" variant="soft" size="sm">
            {{ statusLabel(a.status) }}
          </UBadge>
        </div>

        <div v-if="open !== a.znuny_ticket_id" class="mt-4 flex gap-2">
          <UButton
            color="success"
            variant="soft"
            icon="i-lucide-check"
            label="Aprovar"
            @click="start(a.znuny_ticket_id, 'approved')"
          />
          <UButton
            color="error"
            variant="soft"
            icon="i-lucide-x"
            label="Reprovar"
            @click="start(a.znuny_ticket_id, 'rejected')"
          />
          <UButton
            :to="`/tickets/${a.znuny_ticket_id}`"
            color="neutral"
            variant="ghost"
            icon="i-lucide-external-link"
            label="Ver o chamado"
          />
        </div>

        <div v-else class="mt-4 space-y-3">
          <UFormField
            :label="decision === 'rejected' ? 'Por que não foi aprovado?' : 'Observação (opcional)'"
            :help="decision === 'rejected'
              ? 'O autor lê este texto no próprio chamado.'
              : 'Fica registrado no chamado.'"
          >
            <UTextarea v-model="reason" :rows="3" class="w-full" />
          </UFormField>

          <ul v-if="errors.length" class="list-disc pl-5 text-sm text-error">
            <li v-for="err in errors" :key="err">{{ err }}</li>
          </ul>

          <div class="flex gap-2">
            <UButton
              :color="decision === 'approved' ? 'success' : 'error'"
              :loading="saving"
              :disabled="errors.length > 0"
              :label="decision === 'approved' ? 'Confirmar aprovação' : 'Confirmar reprovação'"
              @click="submit(a.znuny_ticket_id)"
            />
            <UButton color="neutral" variant="ghost" label="Cancelar" @click="open = null" />
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>
