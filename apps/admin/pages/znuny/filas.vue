<script setup lang="ts">
// Spec #4 — Filas de atendimento do Znuny. Esta tela lê e escreve AO VIVO no
// Znuny via GI (proxy `/api/admin/znuny/objects/Queue`); o console não guarda
// nenhuma cópia. Não existe exclusão de fila no Znuny — "Invalidar" é
// ValidID=2, nunca "Excluir". Toda escrita mostra o 422 do Znuny como veio.
import {
  buildInvalidateQueuePayload,
  buildQueuePayload,
  emptyQueueDraft,
  extractItemId,
  extractItems,
  extractSupport,
  followUpOptions,
  formatMinutes,
  missingQueueSupportLists,
  optionsWithCurrent,
  queueDraftFromItem,
  toOptions,
  validateQueueDraft,
  validBadgeColor,
  validLabelPt,
  type QueueDraft,
} from '../../composables/useZnunyObject'

definePageMeta({ middleware: 'admin-auth' })

interface QueueRow extends QueueDraft {
  id: string
}

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const { data: raw, pending, refresh } = await useAsyncData('znuny-queues', () =>
  $fetch<unknown>('/api/admin/znuny/objects/Queue', { headers }).catch(() => null))

const loadFailed = computed(() => !pending.value && raw.value === null)

const rows = computed<QueueRow[]>(() =>
  extractItems(raw.value, 'Queue').map(item => ({
    id: extractItemId(item),
    ...queueDraftFromItem(item),
  })),
)
const isEmpty = computed(() => !pending.value && !loadFailed.value && rows.value.length === 0)

const support = computed(() => extractSupport(raw.value))
const groupOptions = computed(() => toOptions(support.value.GroupList))
const validOptions = computed(() => toOptions(support.value.ValidList))
const calendarOptions = computed(() => toOptions(support.value.CalendarList))
// Listas de apoio dos campos obrigatórios da fila (endereço de resposta,
// saudação, assinatura) — vêm do mesmo `support` da listagem.
const systemAddressOptions = computed(() => toOptions(support.value.SystemAddressList))
const missingSupport = computed(() =>
  pending.value || loadFailed.value ? [] : missingQueueSupportLists(support.value))

function groupName(id: string): string {
  return groupOptions.value.find(o => o.id === id)?.name ?? id ?? '—'
}
function validName(id: string): string {
  const raw = validOptions.value.find(o => o.id === id)?.name ?? id
  return validLabelPt(raw)
}
function systemAddressName(id: string): string {
  if (!id) return '—'
  return systemAddressOptions.value.find(o => o.id === id)?.name ?? `#${id}`
}

// --- Criar / editar -----------------------------------------------------
const formOpen = ref(false)
const editingId = ref<string | null>(null)
const draft = reactive<QueueDraft>(emptyQueueDraft())
const formError = ref('')
const submitting = ref(false)

function openCreate() {
  editingId.value = null
  Object.assign(draft, emptyQueueDraft())
  formError.value = ''
  formOpen.value = true
}
function openEdit(row: QueueRow) {
  editingId.value = row.id
  Object.assign(draft, queueDraftFromItem(row))
  formError.value = ''
  formOpen.value = true
}

const formErrors = computed(() => validateQueueDraft(draft))

// Selects dos quatro campos que o Znuny exige na criação. `optionsWithCurrent`
// mantém o valor da fila em edição na lista mesmo quando ele não veio no
// `support` — abrir a edição não pode apagar o endereço de resposta da fila.
function selectItems(options: { id: string, name: string }[]) {
  return options.map(o => ({ label: o.name, value: o.id }))
}
const systemAddressItems = computed(() =>
  selectItems(optionsWithCurrent(support.value.SystemAddressList, draft.SystemAddressID)))
const salutationItems = computed(() =>
  selectItems(optionsWithCurrent(support.value.SalutationList, draft.SalutationID)))
const signatureItems = computed(() =>
  selectItems(optionsWithCurrent(support.value.SignatureList, draft.SignatureID)))
const followUpItems = computed(() => selectItems(followUpOptions(draft.FollowUpID)))

async function submit() {
  formError.value = ''
  if (formErrors.value.length > 0) {
    formError.value = formErrors.value[0]!
    return
  }
  submitting.value = true
  try {
    const payload = buildQueuePayload(draft)
    if (editingId.value) {
      await $fetch(`/api/admin/znuny/objects/Queue/${editingId.value}`, { method: 'PUT', body: payload })
      toast.add({ title: 'Fila atualizada no Znuny', color: 'success' })
    }
    else {
      await $fetch('/api/admin/znuny/objects/Queue', { method: 'POST', body: payload })
      toast.add({ title: 'Fila criada no Znuny', color: 'success' })
    }
    formOpen.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    formError.value = err.data?.detail
      ?? (err.statusCode === 422 ? 'O Znuny recusou os dados enviados.' : 'Falha ao salvar a fila. Tente novamente.')
  }
  finally {
    submitting.value = false
  }
}

// --- Invalidar (ValidID=2) — nunca exclusão -----------------------------
const invalidateTarget = ref<QueueRow | null>(null)
const invalidateConfirmText = ref('')
const invalidateOpen = ref(false)
const invalidating = ref(false)
const invalidateError = ref('')

function openInvalidate(row: QueueRow) {
  invalidateTarget.value = row
  invalidateConfirmText.value = ''
  invalidateError.value = ''
  invalidateOpen.value = true
}

const canConfirmInvalidate = computed(() =>
  !!invalidateTarget.value && invalidateConfirmText.value.trim() === invalidateTarget.value.Name)

async function confirmInvalidate() {
  if (!invalidateTarget.value || !canConfirmInvalidate.value) return
  invalidating.value = true
  invalidateError.value = ''
  try {
    const payload = buildInvalidateQueuePayload(queueDraftFromItem(invalidateTarget.value))
    await $fetch(`/api/admin/znuny/objects/Queue/${invalidateTarget.value.id}`, { method: 'PUT', body: payload })
    toast.add({ title: 'Fila invalidada', color: 'neutral' })
    invalidateOpen.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    invalidateError.value = err.data?.detail ?? 'Falha ao invalidar a fila. Tente novamente.'
  }
  finally {
    invalidating.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <header class="mb-4">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Filas de atendimento
      </h1>
      <p class="mt-1 text-sm text-muted">
        Filas do Znuny — grupo responsável e tempos de SLA por fila.
      </p>
    </header>

    <UAlert
      color="warning"
      variant="soft"
      icon="i-lucide-radio"
      title="Esta tela edita o Znuny ao vivo"
      description="Não há rascunho nem desfazer: criar, editar ou invalidar aqui muda a configuração do Znuny na hora."
      class="mb-6"
    />

    <!-- Sem endereço de resposta / saudação / assinatura o Znuny recusa criar
         qualquer fila. Dizer isso é melhor que um select vazio sem explicação. -->
    <UAlert
      v-if="missingSupport.length > 0"
      color="error"
      variant="soft"
      icon="i-lucide-alert-triangle"
      title="Não dá para criar fila agora"
      :description="`O Znuny não devolveu ${missingSupport.join(', ')}. Cadastre esses itens no Znuny (ou verifique a integração) antes de criar uma fila — a criação exige os três.`"
      class="mb-6"
      data-testid="queue-missing-support"
    />

    <div class="mb-6 flex justify-end">
      <UButton color="primary" icon="i-lucide-plus" @click="openCreate">
        Nova fila
      </UButton>
    </div>

    <!-- Carregando -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 3" :key="n" class="h-16 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar as filas</p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refresh()">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <!-- Vazio -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-inbox" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nenhuma fila ainda</p>
        <p class="text-sm text-muted">Crie a primeira fila de atendimento do Znuny.</p>
        <UButton color="primary" icon="i-lucide-plus" class="mt-1" @click="openCreate">
          Nova fila
        </UButton>
      </div>
    </UCard>

    <!-- Lista -->
    <div v-else class="overflow-hidden rounded-xl border border-default">
      <table class="w-full text-sm" data-testid="queue-table">
        <thead class="bg-elevated text-left text-xs uppercase text-muted">
          <tr>
            <th class="px-4 py-2.5">Nome</th>
            <th class="px-4 py-2.5">Grupo</th>
            <th class="px-4 py-2.5">Validade</th>
            <th class="px-4 py-2.5">1ª resposta</th>
            <th class="px-4 py-2.5">Atualização</th>
            <th class="px-4 py-2.5">Solução</th>
            <th class="px-4 py-2.5 text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="border-t border-default">
            <td class="px-4 py-3">
              <span class="font-semibold text-highlighted">{{ row.Name }}</span>
              <span class="block text-xs text-dimmed">responde como {{ systemAddressName(row.SystemAddressID) }}</span>
            </td>
            <td class="px-4 py-3 text-muted">{{ groupName(row.GroupID) }}</td>
            <td class="px-4 py-3">
              <UBadge :color="validBadgeColor(row.ValidID)" variant="soft" size="sm">
                {{ validName(row.ValidID) }}
              </UBadge>
            </td>
            <td class="px-4 py-3 text-muted">{{ formatMinutes(row.FirstResponseTime) }}</td>
            <td class="px-4 py-3 text-muted">{{ formatMinutes(row.UpdateTime) }}</td>
            <td class="px-4 py-3 text-muted">{{ formatMinutes(row.SolutionTime) }}</td>
            <td class="px-4 py-3">
              <div class="flex justify-end gap-2">
                <UButton size="xs" color="neutral" variant="soft" icon="i-lucide-pencil" @click="openEdit(row)">
                  Editar
                </UButton>
                <UButton
                  v-if="row.ValidID !== '2'"
                  size="xs"
                  color="error"
                  variant="soft"
                  icon="i-lucide-ban"
                  @click="openInvalidate(row)"
                >
                  Invalidar
                </UButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal criar/editar -->
    <UModal
      v-model:open="formOpen"
      :title="editingId ? 'Editar fila' : 'Nova fila'"
      description="Alterações aqui são gravadas direto no Znuny."
      :ui="{ content: 'max-w-2xl', footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert v-if="formError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="formError" />

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Nome" required>
              <UInput v-model="draft.Name" placeholder="ex.: Suporte N1" class="w-full" />
            </UFormField>
            <UFormField label="Grupo" required>
              <USelect
                v-model="draft.GroupID"
                :items="groupOptions.map(o => ({ label: o.name, value: o.id }))"
                placeholder="Selecione o grupo"
                class="w-full"
              />
            </UFormField>
          </div>

          <UFormField label="Comentário">
            <UTextarea v-model="draft.Comment" :rows="2" class="w-full" />
          </UFormField>

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Validade" required>
              <USelect
                v-model="draft.ValidID"
                :items="validOptions.map(o => ({ label: validLabelPt(o.name), value: o.id }))"
                class="w-full"
              />
            </UFormField>
            <UFormField label="Calendário">
              <USelect
                v-model="draft.Calendar"
                :items="[{ label: 'Padrão (sem calendário específico)', value: '' }, ...calendarOptions.map(o => ({ label: o.name, value: o.id }))]"
                class="w-full"
              />
            </UFormField>
          </div>

          <div class="grid gap-4 sm:grid-cols-3">
            <UFormField label="1ª resposta (min)" :help="formatMinutes(draft.FirstResponseTime)">
              <UInput v-model="draft.FirstResponseTime" type="number" min="0" class="w-full" />
            </UFormField>
            <UFormField label="Atualização (min)" :help="formatMinutes(draft.UpdateTime)">
              <UInput v-model="draft.UpdateTime" type="number" min="0" class="w-full" />
            </UFormField>
            <UFormField label="Solução (min)" :help="formatMinutes(draft.SolutionTime)">
              <UInput v-model="draft.SolutionTime" type="number" min="0" class="w-full" />
            </UFormField>
          </div>

          <!-- Obrigatórios do Znuny na criação (RequiredOnAdd da Queue): sem os
               quatro, o QueueAdd recusa. Ids vêm das listas de apoio da própria
               listagem — o operador escolhe pelo nome, nunca digita id. -->
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Endereço de resposta" required help="E-mail com que esta fila responde.">
              <USelect
                v-model="draft.SystemAddressID"
                :items="systemAddressItems"
                placeholder="Selecione o endereço"
                class="w-full"
              />
            </UFormField>
            <UFormField label="Saudação" required help="Abertura padrão das respostas da fila.">
              <USelect
                v-model="draft.SalutationID"
                :items="salutationItems"
                placeholder="Selecione a saudação"
                class="w-full"
              />
            </UFormField>
          </div>

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Assinatura" required help="Fechamento padrão das respostas da fila.">
              <USelect
                v-model="draft.SignatureID"
                :items="signatureItems"
                placeholder="Selecione a assinatura"
                class="w-full"
              />
            </UFormField>
            <UFormField label="Follow-up" required help="O que fazer quando o cliente responde um chamado fechado.">
              <USelect
                v-model="draft.FollowUpID"
                :items="followUpItems"
                placeholder="Selecione o tratamento"
                class="w-full"
              />
            </UFormField>
          </div>

          <UFormField label="Timeout de desbloqueio (min)" :help="formatMinutes(draft.UnlockTimeout)">
            <UInput v-model="draft.UnlockTimeout" type="number" min="0" class="w-full" />
          </UFormField>

          <!-- Botão desabilitado sem explicação trava o operador — a primeira
               pendência fica visível enquanto ela existir. -->
          <p v-if="formErrors.length > 0" class="text-xs text-muted" data-testid="queue-form-pending">
            Antes de salvar: {{ formErrors[0] }}
            <span v-if="formErrors.length > 1">(+{{ formErrors.length - 1 }} pendência(s))</span>
          </p>
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="submitting" @click="formOpen = false" />
        <UButton
          :label="editingId ? 'Salvar alterações' : 'Criar fila'"
          color="primary"
          icon="i-lucide-check"
          :loading="submitting"
          :disabled="formErrors.length > 0"
          @click="submit"
        />
      </template>
    </UModal>

    <!-- Modal invalidar -->
    <UModal
      v-model:open="invalidateOpen"
      title="Invalidar fila"
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-3">
          <UAlert
            color="warning"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="O Znuny não exclui filas — isto marca a fila como inválida (ValidID = 2)."
            description="A fila deixa de aparecer para novos tickets, mas o histórico continua íntegro."
          />
          <UAlert v-if="invalidateError" color="error" variant="soft" :title="invalidateError" />
          <p class="text-sm text-default">
            Para confirmar, digite o nome da fila:
            <span class="font-semibold text-highlighted">{{ invalidateTarget?.Name }}</span>
          </p>
          <UInput v-model="invalidateConfirmText" placeholder="digite o nome aqui" class="w-full" />
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="invalidating" @click="invalidateOpen = false" />
        <UButton
          label="Invalidar fila"
          color="error"
          icon="i-lucide-ban"
          :loading="invalidating"
          :disabled="!canConfirmInvalidate"
          @click="confirmInvalidate"
        />
      </template>
    </UModal>
  </div>
</template>
