<script setup lang="ts">
// Spec #4 — Políticas de SLA do Znuny. Lê e escreve AO VIVO via GI (proxy
// `/api/admin/znuny/objects/SLA`); o console não guarda cópia. Tempos são
// minutos — sempre rotulados com a unidade e o equivalente em horas. Não
// existe exclusão de SLA no Znuny, só invalidar (ValidID=2).
import {
  buildInvalidateSlaPayload,
  buildSlaPayload,
  emptySlaDraft,
  extractItemId,
  extractItems,
  extractSupport,
  formatMinutes,
  slaDraftFromItem,
  toOptions,
  validateSlaDraft,
  validBadgeColor,
  validLabelPt,
  type SlaDraft,
} from '../../composables/useZnunyObject'

definePageMeta({ middleware: 'admin-auth' })

interface SlaRow {
  id: string
  Name: string
  Comment: string
  ValidID: string
  Calendar: string
  FirstResponseTime: string
  FirstResponseNotify: string
  UpdateTime: string
  UpdateNotify: string
  SolutionTime: string
  SolutionNotify: string
  ServiceIDs: string[]
}

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const { data: raw, pending, refresh } = await useAsyncData('znuny-slas', () =>
  $fetch<unknown>('/api/admin/znuny/objects/SLA', { headers }).catch(() => null))

// Serviços entram só para popular o multi-select de ServiceIDs — não fazem
// parte das listas de apoio de SLA, então é uma segunda chamada ao mesmo
// proxy genérico.
const { data: servicesRaw } = await useAsyncData('znuny-services-for-sla', () =>
  $fetch<unknown>('/api/admin/znuny/objects/Service', { headers }).catch(() => null))

const loadFailed = computed(() => !pending.value && raw.value === null)

const rows = computed<SlaRow[]>(() =>
  extractItems(raw.value, 'SLA').map(item => ({
    id: extractItemId(item),
    ...slaDraftFromItem(item),
  })),
)
const isEmpty = computed(() => !pending.value && !loadFailed.value && rows.value.length === 0)

const support = computed(() => extractSupport(raw.value))
const validOptions = computed(() => toOptions(support.value.ValidList))
const calendarOptions = computed(() => toOptions(support.value.CalendarList))

const serviceOptions = computed(() =>
  extractItems(servicesRaw.value, 'Service').map(item => ({
    id: extractItemId(item),
    name: String(item.Name ?? extractItemId(item)),
  })),
)

function validName(id: string): string {
  const raw = validOptions.value.find(o => o.id === id)?.name ?? id
  return validLabelPt(raw)
}
function serviceNames(ids: string[]): string {
  if (ids.length === 0) return '—'
  return ids
    .map(id => serviceOptions.value.find(o => o.id === id)?.name ?? id)
    .join(', ')
}

// --- Criar / editar -----------------------------------------------------
const formOpen = ref(false)
const editingId = ref<string | null>(null)
const draft = reactive<SlaDraft>(emptySlaDraft())
const formError = ref('')
const submitting = ref(false)

function openCreate() {
  editingId.value = null
  Object.assign(draft, emptySlaDraft())
  formError.value = ''
  formOpen.value = true
}
function openEdit(row: SlaRow) {
  editingId.value = row.id
  Object.assign(draft, slaDraftFromItem(row))
  formError.value = ''
  formOpen.value = true
}

function toggleService(id: string) {
  const idx = draft.ServiceIDs.indexOf(id)
  if (idx === -1) draft.ServiceIDs.push(id)
  else draft.ServiceIDs.splice(idx, 1)
}

const formErrors = computed(() => validateSlaDraft(draft))

async function submit() {
  formError.value = ''
  if (formErrors.value.length > 0) {
    formError.value = formErrors.value[0]!
    return
  }
  submitting.value = true
  try {
    const payload = buildSlaPayload(draft)
    if (editingId.value) {
      await $fetch(`/api/admin/znuny/objects/SLA/${editingId.value}`, { method: 'PUT', body: payload })
      toast.add({ title: 'SLA atualizado no Znuny', color: 'success' })
    }
    else {
      await $fetch('/api/admin/znuny/objects/SLA', { method: 'POST', body: payload })
      toast.add({ title: 'SLA criado no Znuny', color: 'success' })
    }
    formOpen.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    formError.value = err.data?.detail
      ?? (err.statusCode === 422 ? 'O Znuny recusou os dados enviados.' : 'Falha ao salvar o SLA. Tente novamente.')
  }
  finally {
    submitting.value = false
  }
}

// --- Invalidar (ValidID=2) — nunca exclusão -----------------------------
const invalidateTarget = ref<SlaRow | null>(null)
const invalidateConfirmText = ref('')
const invalidateOpen = ref(false)
const invalidating = ref(false)
const invalidateError = ref('')

function openInvalidate(row: SlaRow) {
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
    const payload = buildInvalidateSlaPayload(slaDraftFromItem(invalidateTarget.value))
    await $fetch(`/api/admin/znuny/objects/SLA/${invalidateTarget.value.id}`, { method: 'PUT', body: payload })
    toast.add({ title: 'SLA invalidado', color: 'neutral' })
    invalidateOpen.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    invalidateError.value = err.data?.detail ?? 'Falha ao invalidar o SLA. Tente novamente.'
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
        Políticas de SLA
      </h1>
      <p class="mt-1 text-sm text-muted">
        Tempos de resposta, atualização e solução — e o limiar de notificação de cada um.
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

    <div class="mb-6 flex justify-end">
      <UButton color="primary" icon="i-lucide-plus" @click="openCreate">
        Novo SLA
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
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar os SLAs</p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refresh()">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <!-- Vazio -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-clock" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nenhuma política de SLA ainda</p>
        <p class="text-sm text-muted">Crie a primeira política de SLA do Znuny.</p>
        <UButton color="primary" icon="i-lucide-plus" class="mt-1" @click="openCreate">
          Novo SLA
        </UButton>
      </div>
    </UCard>

    <!-- Lista -->
    <div v-else class="space-y-3" data-testid="sla-list">
      <UCard v-for="row in rows" :key="row.id" :ui="{ body: 'space-y-3' }">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex items-center gap-2">
              <p class="font-display text-base font-bold text-highlighted">{{ row.Name }}</p>
              <UBadge :color="validBadgeColor(row.ValidID)" variant="soft" size="sm">
                {{ validName(row.ValidID) }}
              </UBadge>
            </div>
            <p v-if="row.Comment" class="mt-1 text-sm text-muted">{{ row.Comment }}</p>
          </div>
          <div class="flex gap-2">
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
        </div>

        <div class="grid gap-3 text-sm sm:grid-cols-3">
          <div>
            <p class="text-xs uppercase text-muted">1ª resposta</p>
            <p class="text-default">{{ formatMinutes(row.FirstResponseTime) }}</p>
            <p class="text-xs text-muted">notifica em {{ row.FirstResponseNotify || '—' }}%</p>
          </div>
          <div>
            <p class="text-xs uppercase text-muted">Atualização</p>
            <p class="text-default">{{ formatMinutes(row.UpdateTime) }}</p>
            <p class="text-xs text-muted">notifica em {{ row.UpdateNotify || '—' }}%</p>
          </div>
          <div>
            <p class="text-xs uppercase text-muted">Solução</p>
            <p class="text-default">{{ formatMinutes(row.SolutionTime) }}</p>
            <p class="text-xs text-muted">notifica em {{ row.SolutionNotify || '—' }}%</p>
          </div>
        </div>

        <p class="text-sm text-muted">
          <span class="font-medium text-default">Serviços:</span> {{ serviceNames(row.ServiceIDs) }}
        </p>
      </UCard>
    </div>

    <!-- Modal criar/editar -->
    <UModal
      v-model:open="formOpen"
      :title="editingId ? 'Editar SLA' : 'Novo SLA'"
      description="Alterações aqui são gravadas direto no Znuny."
      :ui="{ content: 'max-w-2xl', footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert v-if="formError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="formError" />

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Nome" required>
              <UInput v-model="draft.Name" placeholder="ex.: SLA Padrão" class="w-full" />
            </UFormField>
            <UFormField label="Validade" required>
              <USelect
                v-model="draft.ValidID"
                :items="validOptions.map(o => ({ label: validLabelPt(o.name), value: o.id }))"
                class="w-full"
              />
            </UFormField>
          </div>

          <UFormField label="Comentário">
            <UTextarea v-model="draft.Comment" :rows="2" class="w-full" />
          </UFormField>

          <UFormField label="Calendário">
            <USelect
              v-model="draft.Calendar"
              :items="[{ label: 'Padrão (sem calendário específico)', value: '' }, ...calendarOptions.map(o => ({ label: o.name, value: o.id }))]"
              class="w-full"
            />
          </UFormField>

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="1ª resposta — tempo (min)" :help="formatMinutes(draft.FirstResponseTime)">
              <UInput v-model="draft.FirstResponseTime" type="number" min="0" class="w-full" />
            </UFormField>
            <UFormField label="1ª resposta — notificar em (%)" help="Percentual do prazo antes de alertar.">
              <UInput v-model="draft.FirstResponseNotify" type="number" min="0" max="100" class="w-full" />
            </UFormField>

            <UFormField label="Atualização — tempo (min)" :help="formatMinutes(draft.UpdateTime)">
              <UInput v-model="draft.UpdateTime" type="number" min="0" class="w-full" />
            </UFormField>
            <UFormField label="Atualização — notificar em (%)">
              <UInput v-model="draft.UpdateNotify" type="number" min="0" max="100" class="w-full" />
            </UFormField>

            <UFormField label="Solução — tempo (min)" :help="formatMinutes(draft.SolutionTime)">
              <UInput v-model="draft.SolutionTime" type="number" min="0" class="w-full" />
            </UFormField>
            <UFormField label="Solução — notificar em (%)">
              <UInput v-model="draft.SolutionNotify" type="number" min="0" max="100" class="w-full" />
            </UFormField>
          </div>

          <UFormField label="Serviços cobertos por este SLA">
            <div v-if="serviceOptions.length === 0" class="text-sm text-muted">
              Nenhum serviço cadastrado no Znuny ainda.
            </div>
            <div v-else class="grid gap-2 sm:grid-cols-2">
              <UCheckbox
                v-for="s in serviceOptions"
                :key="s.id"
                :model-value="draft.ServiceIDs.includes(s.id)"
                :label="s.name"
                @update:model-value="toggleService(s.id)"
              />
            </div>
          </UFormField>
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="submitting" @click="formOpen = false" />
        <UButton
          :label="editingId ? 'Salvar alterações' : 'Criar SLA'"
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
      title="Invalidar SLA"
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-3">
          <UAlert
            color="warning"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="O Znuny não exclui SLAs — isto marca o SLA como inválido (ValidID = 2)."
            description="Tickets já vinculados mantêm o histórico; novos tickets deixam de usar este SLA."
          />
          <UAlert v-if="invalidateError" color="error" variant="soft" :title="invalidateError" />
          <p class="text-sm text-default">
            Para confirmar, digite o nome do SLA:
            <span class="font-semibold text-highlighted">{{ invalidateTarget?.Name }}</span>
          </p>
          <UInput v-model="invalidateConfirmText" placeholder="digite o nome aqui" class="w-full" />
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="invalidating" @click="invalidateOpen = false" />
        <UButton
          label="Invalidar SLA"
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
