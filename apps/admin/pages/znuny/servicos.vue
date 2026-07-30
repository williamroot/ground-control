<script setup lang="ts">
// Serviços do Znuny (Spec #4, Bloco A) — capa de administração: lê e escreve
// AO VIVO via GI (proxy `/api/admin/znuny/objects/Service`, dono: A1). O
// console não guarda nada — zero rascunho, zero desfazer, cada gravação
// aplica imediatamente no Znuny. Hierarquia via ParentID (guarda anti-ciclo
// em `useServiceTree`); "Invalidar" (ValidID=2) é a única forma de remoção
// (Bloco A não tem delete real) e exige confirmação digitando o nome.
import ServiceTreeRow from '../../components/znuny/ServiceTreeRow.vue'
import {
  buildInvalidateServicePayload,
  buildServicePayload,
  buildServiceTree,
  emptyServiceDraft,
  flattenServiceTree,
  parentOptions,
  serviceDraftFromRow,
  serviceRowFromItem,
  validateServiceDraft,
  type ServiceDraft,
  type ServiceRow,
} from '../../composables/useServiceTree'
import {
  extractItemId,
  extractItems,
  extractSupport,
  toOptions,
  validLabelPt,
} from '../../composables/useZnunyObject'

definePageMeta({ middleware: 'admin-auth' })

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const { data: raw, pending, refresh } = await useAsyncData('znuny-services', () =>
  $fetch<unknown>('/api/admin/znuny/objects/Service', { headers }).catch(() => null))

const loadFailed = computed(() => !pending.value && raw.value === null)

const services = computed<ServiceRow[]>(() =>
  extractItems(raw.value, 'Service').map(item => serviceRowFromItem(item, extractItemId(item))))
const isEmpty = computed(() => !pending.value && !loadFailed.value && services.value.length === 0)

const support = computed(() => extractSupport(raw.value))
const validOptions = computed(() => toOptions(support.value.ValidList))
function validLabel(validId: string): string {
  const raw = validOptions.value.find(o => o.id === validId)?.name ?? validId
  return validLabelPt(raw)
}

const treeRows = computed(() => flattenServiceTree(buildServiceTree(services.value)))

// --- Formulário criar/editar --------------------------------------------------
const formOpen = ref(false)
const editingId = ref<string | null>(null)
const draft = reactive<ServiceDraft>(emptyServiceDraft())
const formError = ref('')
const submitting = ref(false)

const parentSelectOptions = computed(() => parentOptions(services.value, editingId.value))
const validSelectOptions = computed(() =>
  validOptions.value.map(o => ({ label: validLabelPt(o.name), value: o.id })))

function openCreate() {
  editingId.value = null
  Object.assign(draft, emptyServiceDraft())
  formError.value = ''
  formOpen.value = true
}

function openEdit(row: ServiceRow) {
  editingId.value = row.id
  Object.assign(draft, serviceDraftFromRow(row))
  formError.value = ''
  formOpen.value = true
}

const formErrors = computed(() => validateServiceDraft(draft))

async function submit() {
  formError.value = ''
  if (formErrors.value.length > 0) {
    formError.value = formErrors.value[0]!
    return
  }

  submitting.value = true
  try {
    const payload = buildServicePayload(draft)
    if (editingId.value) {
      await $fetch(`/api/admin/znuny/objects/Service/${editingId.value}`, { method: 'PUT', body: payload })
      toast.add({ title: 'Serviço atualizado no Znuny', color: 'success' })
    }
    else {
      await $fetch('/api/admin/znuny/objects/Service', { method: 'POST', body: payload })
      toast.add({ title: 'Serviço criado no Znuny', color: 'success' })
    }
    formOpen.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    formError.value = err.data?.detail
      ?? (err.statusCode === 422 ? 'O Znuny recusou os dados enviados.' : 'Falha ao salvar no Znuny. Tente novamente.')
  }
  finally {
    submitting.value = false
  }
}

// --- Invalidar (ValidID=2) — nunca exclusão -----------------------------
const invalidateTarget = ref<ServiceRow | null>(null)
const invalidateConfirmText = ref('')
const invalidateOpen = ref(false)
const invalidating = ref(false)
const invalidateError = ref('')

function openInvalidate(row: ServiceRow) {
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
    const payload = buildInvalidateServicePayload(serviceDraftFromRow(invalidateTarget.value))
    await $fetch(`/api/admin/znuny/objects/Service/${invalidateTarget.value.id}`, { method: 'PUT', body: payload })
    toast.add({ title: 'Serviço invalidado no Znuny', color: 'neutral' })
    invalidateOpen.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    invalidateError.value = err.data?.detail ?? 'Falha ao invalidar o serviço. Tente novamente.'
  }
  finally {
    invalidating.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <header class="mb-4 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Serviços
        </h1>
        <p class="mt-1 text-sm text-muted">
          Catálogo de serviços do Znuny, com hierarquia por serviço-pai.
        </p>
      </div>
      <UButton color="primary" icon="i-lucide-plus" @click="openCreate">
        Novo serviço
      </UButton>
    </header>

    <UAlert
      color="warning"
      variant="soft"
      icon="i-lucide-alert-triangle"
      title="Esta tela edita o Znuny ao vivo"
      description="Não há rascunho nem desfazer: criar, editar ou invalidar aqui muda a configuração do Znuny na hora."
      class="mb-6"
    />

    <!-- Carregando -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 4" :key="n" class="h-12 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar os serviços</p>
        <p class="max-w-sm text-sm text-muted">Verifique se o Znuny está disponível e tente novamente.</p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refresh()">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <!-- Vazio -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-network" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nenhum serviço ainda</p>
        <p class="text-sm text-muted">Crie o primeiro serviço no Znuny.</p>
        <UButton color="primary" icon="i-lucide-plus" class="mt-1" @click="openCreate">
          Novo serviço
        </UButton>
      </div>
    </UCard>

    <!-- Árvore -->
    <div v-else class="overflow-hidden rounded-xl border border-default">
      <table class="w-full text-sm" data-testid="service-table">
        <thead class="bg-elevated text-left text-xs uppercase text-muted">
          <tr>
            <th class="px-4 py-2.5">Nome</th>
            <th class="px-4 py-2.5">Comentário</th>
            <th class="px-4 py-2.5">Validade</th>
            <th class="px-4 py-2.5 text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          <ServiceTreeRow
            v-for="node in treeRows"
            :key="node.row.id"
            :row="node.row"
            :leaf-name="node.leafName"
            :depth="node.depth"
            :valid-label="validLabel(node.row.ValidID)"
            @edit="openEdit(node.row)"
            @invalidate="openInvalidate(node.row)"
          />
        </tbody>
      </table>
    </div>

    <!-- Modal criar/editar -->
    <UModal
      v-model:open="formOpen"
      :title="editingId ? 'Editar serviço' : 'Novo serviço'"
      description="Alterações aqui são gravadas direto no Znuny."
      :ui="{ content: 'max-w-xl', footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert v-if="formError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="formError" />

          <UFormField label="Nome" required help="apenas o nível atual — a hierarquia vem do campo Pai">
            <UInput v-model="draft.name" placeholder="ex.: Suporte" class="w-full" />
          </UFormField>

          <UFormField label="Serviço pai" help="não é possível escolher o próprio serviço ou um descendente dele">
            <USelect v-model="draft.parentId" :items="parentSelectOptions" class="w-full" />
          </UFormField>

          <UFormField label="Comentário">
            <UTextarea v-model="draft.comment" :rows="2" class="w-full" />
          </UFormField>

          <div class="grid gap-4 sm:grid-cols-3">
            <UFormField label="Validade" required>
              <USelect v-model="draft.validId" :items="validSelectOptions" class="w-full" />
            </UFormField>
            <UFormField label="Tipo (id)" help="id do tipo de serviço no Znuny">
              <UInput v-model="draft.typeId" class="w-full" />
            </UFormField>
            <UFormField label="Criticidade">
              <UInput v-model="draft.criticality" class="w-full" />
            </UFormField>
          </div>
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="submitting" @click="formOpen = false" />
        <UButton
          :label="editingId ? 'Salvar alterações' : 'Criar serviço'"
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
      title="Invalidar serviço"
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-3">
          <UAlert
            color="warning"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="O Znuny não exclui serviços — isto marca o serviço como inválido (ValidID = 2)."
            description="O serviço deixa de aparecer para novos tickets, mas o histórico continua íntegro."
          />
          <UAlert v-if="invalidateError" color="error" variant="soft" :title="invalidateError" />
          <p class="text-sm text-default">
            Para confirmar, digite o nome do serviço:
            <span class="font-semibold text-highlighted">{{ invalidateTarget?.Name }}</span>
          </p>
          <UInput v-model="invalidateConfirmText" placeholder="digite o nome aqui" class="w-full" />
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="invalidating" @click="invalidateOpen = false" />
        <UButton
          label="Invalidar serviço"
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
