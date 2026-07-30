<script setup lang="ts">
// Classificação do Znuny (Spec #4, Bloco A) — três abas na mesma tela: Tipos
// de chamado, Estados e Prioridades. Lê e escreve AO VIVO via GI (proxy
// `/api/admin/znuny/objects/{Type|State|Priority}`, dono: A1). Zero rascunho,
// zero desfazer. "Invalidar" (ValidID=2) é a única forma de remoção e exige
// confirmação digitando o nome (compartilhada pelas três abas).
import ClassificationRow from '../../components/znuny/ClassificationRow.vue'
import {
  buildInvalidatePriorityPayload,
  buildInvalidateStatePayload,
  buildInvalidateTypePayload,
  buildPriorityPayload,
  buildStatePayload,
  buildTypePayload,
  emptyPriorityDraft,
  emptyStateDraft,
  emptyTypeDraft,
  priorityDraftFromItem,
  stateDraftFromItem,
  typeDraftFromItem,
  validateStateDraft,
  validateTypeDraft,
  type PriorityDraft,
  type StateDraft,
  type TypeDraft,
} from '../../composables/useZnunyClassification'
import {
  extractItemId,
  extractItems,
  extractSupport,
  toOptions,
  validLabelPt,
} from '../../composables/useZnunyObject'

definePageMeta({ middleware: 'admin-auth' })

interface TypeRow extends TypeDraft { id: string }
interface StateRow extends StateDraft { id: string }
type PriorityRow = TypeRow

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

type TabKey = 'tipos' | 'estados' | 'prioridades'
const activeTab = ref<TabKey>('tipos')
const tabs: { key: TabKey, label: string }[] = [
  { key: 'tipos', label: 'Tipos de chamado' },
  { key: 'estados', label: 'Estados' },
  { key: 'prioridades', label: 'Prioridades' },
]

// --- Carregamento --------------------------------------------------------------
const { data: typesRaw, pending: typesPending, refresh: refreshTypes } = await useAsyncData(
  'znuny-types',
  () => $fetch<unknown>('/api/admin/znuny/objects/Type', { headers }).catch(() => null),
)
const { data: statesRaw, pending: statesPending, refresh: refreshStates } = await useAsyncData(
  'znuny-states',
  () => $fetch<unknown>('/api/admin/znuny/objects/State', { headers }).catch(() => null),
)
const { data: prioritiesRaw, pending: prioritiesPending, refresh: refreshPriorities } = await useAsyncData(
  'znuny-priorities',
  () => $fetch<unknown>('/api/admin/znuny/objects/Priority', { headers }).catch(() => null),
)

const types = computed<TypeRow[]>(() =>
  extractItems(typesRaw.value, 'Type').map(item => ({ id: extractItemId(item), ...typeDraftFromItem(item) })))
const states = computed<StateRow[]>(() =>
  extractItems(statesRaw.value, 'State').map(item => ({ id: extractItemId(item), ...stateDraftFromItem(item) })))
const priorities = computed<PriorityRow[]>(() =>
  extractItems(prioritiesRaw.value, 'Priority').map(item => ({ id: extractItemId(item), ...priorityDraftFromItem(item) })))

const typesFailed = computed(() => !typesPending.value && typesRaw.value === null)
const statesFailed = computed(() => !statesPending.value && statesRaw.value === null)
const prioritiesFailed = computed(() => !prioritiesPending.value && prioritiesRaw.value === null)

const typesEmpty = computed(() => !typesPending.value && !typesFailed.value && types.value.length === 0)
const statesEmpty = computed(() => !statesPending.value && !statesFailed.value && states.value.length === 0)
const prioritiesEmpty = computed(() => !prioritiesPending.value && !prioritiesFailed.value && priorities.value.length === 0)

const typeValidOptions = computed(() => toOptions(extractSupport(typesRaw.value).ValidList))
const stateValidOptions = computed(() => toOptions(extractSupport(statesRaw.value).ValidList))
const priorityValidOptions = computed(() => toOptions(extractSupport(prioritiesRaw.value).ValidList))
const stateTypeOptions = computed(() => toOptions(extractSupport(statesRaw.value).StateTypeList))

function validLabel(options: { id: string, name: string }[], id: string): string {
  const raw = options.find(o => o.id === id)?.name ?? id
  return validLabelPt(raw)
}
function optionLabel(options: { id: string, name: string }[], id: string): string {
  return options.find(o => o.id === id)?.name ?? id
}

// --- Formulário: Tipo -----------------------------------------------------------
const typeFormOpen = ref(false)
const editingTypeId = ref<string | null>(null)
const typeDraft = reactive<TypeDraft>(emptyTypeDraft())
const typeFormError = ref('')
const typeSubmitting = ref(false)
const typeFormErrors = computed(() => validateTypeDraft(typeDraft))

function openCreateType() {
  editingTypeId.value = null
  Object.assign(typeDraft, emptyTypeDraft())
  typeFormError.value = ''
  typeFormOpen.value = true
}
function openEditType(row: TypeRow) {
  editingTypeId.value = row.id
  Object.assign(typeDraft, { name: row.name, validId: row.validId })
  typeFormError.value = ''
  typeFormOpen.value = true
}
async function submitType() {
  typeFormError.value = ''
  if (typeFormErrors.value.length > 0) {
    typeFormError.value = typeFormErrors.value[0]!
    return
  }
  typeSubmitting.value = true
  try {
    const payload = buildTypePayload(typeDraft)
    if (editingTypeId.value) {
      await $fetch(`/api/admin/znuny/objects/Type/${editingTypeId.value}`, { method: 'PUT', body: payload })
      toast.add({ title: 'Tipo de chamado atualizado no Znuny', color: 'success' })
    }
    else {
      await $fetch('/api/admin/znuny/objects/Type', { method: 'POST', body: payload })
      toast.add({ title: 'Tipo de chamado criado no Znuny', color: 'success' })
    }
    typeFormOpen.value = false
    await refreshTypes()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    typeFormError.value = err.data?.detail
      ?? (err.statusCode === 422 ? 'O Znuny recusou os dados enviados.' : 'Falha ao salvar no Znuny. Tente novamente.')
  }
  finally {
    typeSubmitting.value = false
  }
}

// --- Formulário: Estado ----------------------------------------------------------
const stateFormOpen = ref(false)
const editingStateId = ref<string | null>(null)
const stateDraft = reactive<StateDraft>(emptyStateDraft())
const stateFormError = ref('')
const stateSubmitting = ref(false)
const stateFormErrors = computed(() => validateStateDraft(stateDraft))

function openCreateState() {
  editingStateId.value = null
  Object.assign(stateDraft, emptyStateDraft())
  stateFormError.value = ''
  stateFormOpen.value = true
}
function openEditState(row: StateRow) {
  editingStateId.value = row.id
  Object.assign(stateDraft, { name: row.name, comment: row.comment, validId: row.validId, typeId: row.typeId })
  stateFormError.value = ''
  stateFormOpen.value = true
}
async function submitState() {
  stateFormError.value = ''
  if (stateFormErrors.value.length > 0) {
    stateFormError.value = stateFormErrors.value[0]!
    return
  }
  stateSubmitting.value = true
  try {
    const payload = buildStatePayload(stateDraft)
    if (editingStateId.value) {
      await $fetch(`/api/admin/znuny/objects/State/${editingStateId.value}`, { method: 'PUT', body: payload })
      toast.add({ title: 'Estado atualizado no Znuny', color: 'success' })
    }
    else {
      await $fetch('/api/admin/znuny/objects/State', { method: 'POST', body: payload })
      toast.add({ title: 'Estado criado no Znuny', color: 'success' })
    }
    stateFormOpen.value = false
    await refreshStates()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    stateFormError.value = err.data?.detail
      ?? (err.statusCode === 422 ? 'O Znuny recusou os dados enviados.' : 'Falha ao salvar no Znuny. Tente novamente.')
  }
  finally {
    stateSubmitting.value = false
  }
}

// --- Formulário: Prioridade -------------------------------------------------------
const priorityFormOpen = ref(false)
const editingPriorityId = ref<string | null>(null)
const priorityDraft = reactive<PriorityDraft>(emptyPriorityDraft())
const priorityFormError = ref('')
const prioritySubmitting = ref(false)
const priorityFormErrors = computed(() => validateTypeDraft(priorityDraft))

function openCreatePriority() {
  editingPriorityId.value = null
  Object.assign(priorityDraft, emptyPriorityDraft())
  priorityFormError.value = ''
  priorityFormOpen.value = true
}
function openEditPriority(row: PriorityRow) {
  editingPriorityId.value = row.id
  Object.assign(priorityDraft, { name: row.name, validId: row.validId })
  priorityFormError.value = ''
  priorityFormOpen.value = true
}
async function submitPriority() {
  priorityFormError.value = ''
  if (priorityFormErrors.value.length > 0) {
    priorityFormError.value = priorityFormErrors.value[0]!
    return
  }
  prioritySubmitting.value = true
  try {
    const payload = buildPriorityPayload(priorityDraft)
    if (editingPriorityId.value) {
      await $fetch(`/api/admin/znuny/objects/Priority/${editingPriorityId.value}`, { method: 'PUT', body: payload })
      toast.add({ title: 'Prioridade atualizada no Znuny', color: 'success' })
    }
    else {
      await $fetch('/api/admin/znuny/objects/Priority', { method: 'POST', body: payload })
      toast.add({ title: 'Prioridade criada no Znuny', color: 'success' })
    }
    priorityFormOpen.value = false
    await refreshPriorities()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    priorityFormError.value = err.data?.detail
      ?? (err.statusCode === 422 ? 'O Znuny recusou os dados enviados.' : 'Falha ao salvar no Znuny. Tente novamente.')
  }
  finally {
    prioritySubmitting.value = false
  }
}

// --- Invalidar (ValidID=2) — compartilhado pelas três abas, nunca exclusão -------
interface InvalidateTarget { kind: TabKey, id: string, name: string }
const invalidateTarget = ref<InvalidateTarget | null>(null)
const invalidateConfirmText = ref('')
const invalidateOpen = ref(false)
const invalidating = ref(false)
const invalidateError = ref('')

function openInvalidateType(row: TypeRow) {
  invalidateTarget.value = { kind: 'tipos', id: row.id, name: row.name }
  invalidateConfirmText.value = ''
  invalidateError.value = ''
  invalidateOpen.value = true
}
function openInvalidateState(row: StateRow) {
  invalidateTarget.value = { kind: 'estados', id: row.id, name: row.name }
  invalidateConfirmText.value = ''
  invalidateError.value = ''
  invalidateOpen.value = true
}
function openInvalidatePriority(row: PriorityRow) {
  invalidateTarget.value = { kind: 'prioridades', id: row.id, name: row.name }
  invalidateConfirmText.value = ''
  invalidateError.value = ''
  invalidateOpen.value = true
}

const canConfirmInvalidate = computed(() =>
  !!invalidateTarget.value && invalidateConfirmText.value.trim() === invalidateTarget.value.name)

async function confirmInvalidate() {
  const target = invalidateTarget.value
  if (!target || !canConfirmInvalidate.value) return
  invalidating.value = true
  invalidateError.value = ''
  try {
    if (target.kind === 'tipos') {
      const row = types.value.find(r => r.id === target.id)
      const payload = buildInvalidateTypePayload(row ? { name: row.name, validId: row.validId } : { name: target.name, validId: '1' })
      await $fetch(`/api/admin/znuny/objects/Type/${target.id}`, { method: 'PUT', body: payload })
      await refreshTypes()
    }
    else if (target.kind === 'estados') {
      const row = states.value.find(r => r.id === target.id)
      const payload = buildInvalidateStatePayload(
        row ? { name: row.name, comment: row.comment, validId: row.validId, typeId: row.typeId } : { name: target.name, comment: '', validId: '1', typeId: '' },
      )
      await $fetch(`/api/admin/znuny/objects/State/${target.id}`, { method: 'PUT', body: payload })
      await refreshStates()
    }
    else {
      const row = priorities.value.find(r => r.id === target.id)
      const payload = buildInvalidatePriorityPayload(row ? { name: row.name, validId: row.validId } : { name: target.name, validId: '1' })
      await $fetch(`/api/admin/znuny/objects/Priority/${target.id}`, { method: 'PUT', body: payload })
      await refreshPriorities()
    }
    toast.add({ title: 'Item invalidado no Znuny', color: 'neutral' })
    invalidateOpen.value = false
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    invalidateError.value = err.data?.detail ?? 'Falha ao invalidar no Znuny. Tente novamente.'
  }
  finally {
    invalidating.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <header class="mb-4">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Classificação
      </h1>
      <p class="mt-1 text-sm text-muted">
        Tipos de chamado, estados e prioridades do Znuny.
      </p>
    </header>

    <UAlert
      color="warning"
      variant="soft"
      icon="i-lucide-alert-triangle"
      title="Esta tela edita o Znuny ao vivo"
      description="Não há rascunho nem desfazer: criar, editar ou invalidar aqui muda a configuração do Znuny na hora."
      class="mb-6"
    />

    <div class="mb-6 flex gap-1 border-b border-default">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        :data-testid="`tab-${tab.key}`"
        class="border-b-2 px-4 py-2 text-sm font-medium transition"
        :class="activeTab === tab.key
          ? 'border-primary text-highlighted'
          : 'border-transparent text-muted hover:text-default'"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Aba: Tipos de chamado -->
    <section v-if="activeTab === 'tipos'" data-testid="panel-tipos">
      <div class="mb-4 flex justify-end">
        <UButton color="primary" icon="i-lucide-plus" @click="openCreateType">
          Novo tipo
        </UButton>
      </div>

      <div v-if="typesPending" class="space-y-3">
        <div v-for="n in 3" :key="n" class="h-12 animate-pulse rounded-xl border border-default bg-elevated" />
      </div>
      <UCard v-else-if="typesFailed" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar os tipos</p>
          <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refreshTypes()">
            Tentar novamente
          </UButton>
        </div>
      </UCard>
      <UCard v-else-if="typesEmpty" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-tag" class="h-10 w-10 text-muted" />
          <p class="font-display text-lg font-semibold text-highlighted">Nenhum tipo ainda</p>
          <UButton color="primary" icon="i-lucide-plus" class="mt-1" @click="openCreateType">
            Novo tipo
          </UButton>
        </div>
      </UCard>
      <div v-else class="overflow-hidden rounded-xl border border-default">
        <table class="w-full text-sm" data-testid="type-table">
          <thead class="bg-elevated text-left text-xs uppercase text-muted">
            <tr>
              <th class="px-4 py-2.5">Nome</th>
              <th class="px-4 py-2.5">Validade</th>
              <th class="px-4 py-2.5 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            <ClassificationRow
              v-for="row in types"
              :key="row.id"
              :name="row.name"
              :valid-id="row.validId"
              :valid-label="validLabel(typeValidOptions, row.validId)"
              @edit="openEditType(row)"
              @invalidate="openInvalidateType(row)"
            />
          </tbody>
        </table>
      </div>
    </section>

    <!-- Aba: Estados -->
    <section v-if="activeTab === 'estados'" data-testid="panel-estados">
      <div class="mb-4 flex justify-end">
        <UButton color="primary" icon="i-lucide-plus" @click="openCreateState">
          Novo estado
        </UButton>
      </div>

      <div v-if="statesPending" class="space-y-3">
        <div v-for="n in 3" :key="n" class="h-12 animate-pulse rounded-xl border border-default bg-elevated" />
      </div>
      <UCard v-else-if="statesFailed" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar os estados</p>
          <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refreshStates()">
            Tentar novamente
          </UButton>
        </div>
      </UCard>
      <UCard v-else-if="statesEmpty" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-flag" class="h-10 w-10 text-muted" />
          <p class="font-display text-lg font-semibold text-highlighted">Nenhum estado ainda</p>
          <UButton color="primary" icon="i-lucide-plus" class="mt-1" @click="openCreateState">
            Novo estado
          </UButton>
        </div>
      </UCard>
      <div v-else class="overflow-hidden rounded-xl border border-default">
        <table class="w-full text-sm" data-testid="state-table">
          <thead class="bg-elevated text-left text-xs uppercase text-muted">
            <tr>
              <th class="px-4 py-2.5">Nome</th>
              <th class="px-4 py-2.5">Tipo de estado</th>
              <th class="px-4 py-2.5">Validade</th>
              <th class="px-4 py-2.5 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            <ClassificationRow
              v-for="row in states"
              :key="row.id"
              :name="row.name"
              :valid-id="row.validId"
              :valid-label="validLabel(stateValidOptions, row.validId)"
              @edit="openEditState(row)"
              @invalidate="openInvalidateState(row)"
            >
              <td class="px-4 py-2.5 text-muted">{{ optionLabel(stateTypeOptions, row.typeId) }}</td>
            </ClassificationRow>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Aba: Prioridades -->
    <section v-if="activeTab === 'prioridades'" data-testid="panel-prioridades">
      <div class="mb-4 flex justify-end">
        <UButton color="primary" icon="i-lucide-plus" @click="openCreatePriority">
          Nova prioridade
        </UButton>
      </div>

      <div v-if="prioritiesPending" class="space-y-3">
        <div v-for="n in 3" :key="n" class="h-12 animate-pulse rounded-xl border border-default bg-elevated" />
      </div>
      <UCard v-else-if="prioritiesFailed" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar as prioridades</p>
          <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refreshPriorities()">
            Tentar novamente
          </UButton>
        </div>
      </UCard>
      <UCard v-else-if="prioritiesEmpty" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-signal" class="h-10 w-10 text-muted" />
          <p class="font-display text-lg font-semibold text-highlighted">Nenhuma prioridade ainda</p>
          <UButton color="primary" icon="i-lucide-plus" class="mt-1" @click="openCreatePriority">
            Nova prioridade
          </UButton>
        </div>
      </UCard>
      <div v-else class="overflow-hidden rounded-xl border border-default">
        <table class="w-full text-sm" data-testid="priority-table">
          <thead class="bg-elevated text-left text-xs uppercase text-muted">
            <tr>
              <th class="px-4 py-2.5">Nome</th>
              <th class="px-4 py-2.5">Validade</th>
              <th class="px-4 py-2.5 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            <ClassificationRow
              v-for="row in priorities"
              :key="row.id"
              :name="row.name"
              :valid-id="row.validId"
              :valid-label="validLabel(priorityValidOptions, row.validId)"
              @edit="openEditPriority(row)"
              @invalidate="openInvalidatePriority(row)"
            />
          </tbody>
        </table>
      </div>
    </section>

    <!-- Modal: Tipo -->
    <UModal
      v-model:open="typeFormOpen"
      :title="editingTypeId ? 'Editar tipo de chamado' : 'Novo tipo de chamado'"
      description="Alterações aqui são gravadas direto no Znuny."
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert v-if="typeFormError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="typeFormError" />
          <UFormField label="Nome" required>
            <UInput v-model="typeDraft.name" class="w-full" />
          </UFormField>
          <UFormField label="Validade" required>
            <USelect
              v-model="typeDraft.validId"
              :items="typeValidOptions.map(o => ({ label: validLabelPt(o.name), value: o.id }))"
              class="w-full"
            />
          </UFormField>
        </div>
      </template>
      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="typeSubmitting" @click="typeFormOpen = false" />
        <UButton
          :label="editingTypeId ? 'Salvar alterações' : 'Criar tipo'"
          color="primary"
          icon="i-lucide-check"
          :loading="typeSubmitting"
          :disabled="typeFormErrors.length > 0"
          @click="submitType"
        />
      </template>
    </UModal>

    <!-- Modal: Estado -->
    <UModal
      v-model:open="stateFormOpen"
      :title="editingStateId ? 'Editar estado' : 'Novo estado'"
      description="Alterações aqui são gravadas direto no Znuny."
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert v-if="stateFormError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="stateFormError" />
          <UFormField label="Nome" required>
            <UInput v-model="stateDraft.name" class="w-full" />
          </UFormField>
          <UFormField label="Comentário">
            <UTextarea v-model="stateDraft.comment" :rows="2" class="w-full" />
          </UFormField>
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Tipo de estado" required help="vem do StateTypeList do Znuny">
              <USelect
                v-model="stateDraft.typeId"
                :items="stateTypeOptions.map(o => ({ label: o.name, value: o.id }))"
                class="w-full"
              />
            </UFormField>
            <UFormField label="Validade" required>
              <USelect
                v-model="stateDraft.validId"
                :items="stateValidOptions.map(o => ({ label: validLabelPt(o.name), value: o.id }))"
                class="w-full"
              />
            </UFormField>
          </div>
        </div>
      </template>
      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="stateSubmitting" @click="stateFormOpen = false" />
        <UButton
          :label="editingStateId ? 'Salvar alterações' : 'Criar estado'"
          color="primary"
          icon="i-lucide-check"
          :loading="stateSubmitting"
          :disabled="stateFormErrors.length > 0"
          @click="submitState"
        />
      </template>
    </UModal>

    <!-- Modal: Prioridade -->
    <UModal
      v-model:open="priorityFormOpen"
      :title="editingPriorityId ? 'Editar prioridade' : 'Nova prioridade'"
      description="Alterações aqui são gravadas direto no Znuny."
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert v-if="priorityFormError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="priorityFormError" />
          <UFormField label="Nome" required>
            <UInput v-model="priorityDraft.name" class="w-full" />
          </UFormField>
          <UFormField label="Validade" required>
            <USelect
              v-model="priorityDraft.validId"
              :items="priorityValidOptions.map(o => ({ label: validLabelPt(o.name), value: o.id }))"
              class="w-full"
            />
          </UFormField>
        </div>
      </template>
      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="prioritySubmitting" @click="priorityFormOpen = false" />
        <UButton
          :label="editingPriorityId ? 'Salvar alterações' : 'Criar prioridade'"
          color="primary"
          icon="i-lucide-check"
          :loading="prioritySubmitting"
          :disabled="priorityFormErrors.length > 0"
          @click="submitPriority"
        />
      </template>
    </UModal>

    <!-- Modal invalidar (compartilhado pelas três abas) -->
    <UModal
      v-model:open="invalidateOpen"
      title="Invalidar"
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-3">
          <UAlert
            color="warning"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="O Znuny não exclui este tipo de item — isto marca como inválido (ValidID = 2)."
            description="O item deixa de aparecer para novos tickets, mas o histórico continua íntegro."
          />
          <UAlert v-if="invalidateError" color="error" variant="soft" :title="invalidateError" />
          <p class="text-sm text-default">
            Para confirmar, digite o nome:
            <span class="font-semibold text-highlighted">{{ invalidateTarget?.name }}</span>
          </p>
          <UInput v-model="invalidateConfirmText" placeholder="digite o nome aqui" class="w-full" />
        </div>
      </template>
      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="invalidating" @click="invalidateOpen = false" />
        <UButton
          label="Invalidar"
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
