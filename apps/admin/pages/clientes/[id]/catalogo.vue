<script setup lang="ts">
// Catálogo de Serviços — CRUD do console para o cliente selecionado (Spec #3,
// V2). Ordenado por sort_order; alterna ativo/inativo direto na lista. Nome do
// cliente sempre visível (console cross-tenant, H2).
import {
  buildCatalogItemPayload,
  CATALOG_ICON_OPTIONS,
  catalogDraftFromItem,
  catalogIconLucide,
  emptyCatalogDraft,
  validateCatalogItem,
  type CatalogItemDraft,
  type CatalogItemRow,
} from '../../../composables/useCatalogItem'

definePageMeta({ middleware: 'admin-auth' })

interface TenantBrief { id: string, trade_name: string }

const route = useRoute()
const tenantId = route.params.id as string
const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const { data: tenant } = await useAsyncData(`admin-tenant-brief-catalog-${tenantId}`, () =>
  $fetch<TenantBrief | null>(`/api/admin/tenants/${tenantId}`, { headers }).catch(() => null))

const { data: itemsRes, pending, refresh } = await useAsyncData(
  `admin-catalog-items-${tenantId}`,
  () => $fetch<CatalogItemRow[] | null>(`/api/admin/tenants/${tenantId}/catalog/items`, { headers })
    .catch(() => null),
)

const loadFailed = computed(() => !pending.value && itemsRes.value === null)
const items = computed(() =>
  [...(itemsRes.value ?? [])].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name)))
const isEmpty = computed(() => !pending.value && !loadFailed.value && items.value.length === 0)

// --- Formulário criar/editar -------------------------------------------------
const formOpen = ref(false)
const editingId = ref<string | null>(null)
const draft = reactive<CatalogItemDraft>(emptyCatalogDraft())
const formError = ref('')
const submitting = ref(false)

function openCreate() {
  editingId.value = null
  Object.assign(draft, emptyCatalogDraft())
  formError.value = ''
  formOpen.value = true
}

function openEdit(row: CatalogItemRow) {
  editingId.value = row.id
  Object.assign(draft, catalogDraftFromItem(row))
  formError.value = ''
  formOpen.value = true
}

async function submit() {
  formError.value = ''
  const errors = validateCatalogItem(draft)
  if (errors.length) {
    formError.value = errors[0]!
    return
  }

  submitting.value = true
  try {
    const payload = buildCatalogItemPayload(draft)
    if (editingId.value) {
      await $fetch(`/api/admin/tenants/${tenantId}/catalog/items/${editingId.value}`, {
        method: 'PUT',
        body: payload,
      })
      toast.add({ title: 'Item atualizado', color: 'success' })
    }
    else {
      await $fetch(`/api/admin/tenants/${tenantId}/catalog/items`, {
        method: 'POST',
        body: payload,
      })
      toast.add({ title: 'Item criado', color: 'success' })
    }
    formOpen.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    formError.value
      = err.statusCode === 422
        ? (err.data?.detail || 'Dados inválidos. Confira os campos destacados.')
        : (err.data?.detail || 'Falha ao salvar o item. Tente novamente.')
  }
  finally {
    submitting.value = false
  }
}

async function toggleActive(row: CatalogItemRow) {
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/catalog/items/${row.id}`, {
      method: 'PUT',
      body: buildCatalogItemPayload({ ...catalogDraftFromItem(row), active: !row.active }),
    })
    toast.add({ title: row.active ? 'Item desativado' : 'Item ativado', color: 'neutral' })
    await refresh()
  }
  catch {
    toast.add({ title: 'Falha ao alterar o status do item', color: 'error' })
  }
}

// --- Exclusão com confirmação -----------------------------------------------
const deleteTarget = ref<CatalogItemRow | null>(null)
const deleteConfirmText = ref('')
const deleteOpen = ref(false)
const deleting = ref(false)

function openDelete(row: CatalogItemRow) {
  deleteTarget.value = row
  deleteConfirmText.value = ''
  deleteOpen.value = true
}

const canConfirmDelete = computed(() =>
  !!deleteTarget.value && deleteConfirmText.value.trim() === deleteTarget.value.name)

async function confirmDelete() {
  if (!deleteTarget.value || !canConfirmDelete.value) return
  deleting.value = true
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/catalog/items/${deleteTarget.value.id}`, {
      method: 'DELETE',
    })
    toast.add({ title: 'Item excluído', color: 'neutral' })
    deleteOpen.value = false
    await refresh()
  }
  catch {
    toast.add({ title: 'Falha ao excluir o item', color: 'error' })
  }
  finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <ULink :to="`/clientes/${tenantId}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <header class="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
          Catálogo de Serviços
        </h1>
        <p class="mt-1 text-sm text-muted">
          Cliente: <span class="font-semibold text-default">{{ tenant?.trade_name ?? tenantId }}</span>
        </p>
      </div>
      <UButton color="primary" icon="i-lucide-plus" @click="openCreate">
        Novo item
      </UButton>
    </header>

    <!-- Loading -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 3" :key="n" class="h-16 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar o catálogo</p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refresh()">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <!-- Vazio -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-package" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nenhum item ainda</p>
        <p class="text-sm text-muted">Crie o primeiro item do catálogo de serviços deste cliente.</p>
        <UButton color="primary" icon="i-lucide-plus" class="mt-1" @click="openCreate">
          Novo item
        </UButton>
      </div>
    </UCard>

    <!-- Lista -->
    <div v-else class="overflow-hidden rounded-xl border border-default">
      <table class="w-full text-sm">
        <thead class="bg-elevated text-left text-xs uppercase text-muted">
          <tr>
            <th class="px-4 py-2.5">Ordem</th>
            <th class="px-4 py-2.5">Nome</th>
            <th class="px-4 py-2.5">Categoria</th>
            <th class="px-4 py-2.5">SLA</th>
            <th class="px-4 py-2.5">Ativo</th>
            <th class="px-4 py-2.5 text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id" class="border-t border-default">
            <td class="px-4 py-3 text-muted">{{ it.sort_order }}</td>
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <UIcon :name="catalogIconLucide(it.icon)" class="h-4 w-4 text-muted" />
                <span class="font-semibold text-highlighted">{{ it.name }}</span>
              </div>
            </td>
            <td class="px-4 py-3 text-muted">{{ it.category }}</td>
            <td class="px-4 py-3 text-muted">{{ it.sla_hours ? `${it.sla_hours}h` : '—' }}</td>
            <td class="px-4 py-3">
              <UBadge :color="it.active ? 'success' : 'neutral'" variant="soft" size="sm" class="cursor-pointer" @click="toggleActive(it)">
                {{ it.active ? 'ativo' : 'inativo' }}
              </UBadge>
            </td>
            <td class="px-4 py-3">
              <div class="flex justify-end gap-2">
                <UButton size="xs" color="neutral" variant="soft" icon="i-lucide-pencil" @click="openEdit(it)">
                  Editar
                </UButton>
                <UButton size="xs" color="error" variant="soft" icon="i-lucide-trash-2" @click="openDelete(it)">
                  Excluir
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
      :title="editingId ? 'Editar item' : 'Novo item'"
      :description="`Cliente: ${tenant?.trade_name ?? tenantId}`"
      :ui="{ content: 'max-w-2xl', footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert v-if="formError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="formError" />

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Nome" required>
              <UInput v-model="draft.name" placeholder="Provisionar novo usuário" class="w-full" />
            </UFormField>
            <UFormField label="Categoria" required>
              <UInput v-model="draft.category" placeholder="ex.: contas" class="w-full" />
            </UFormField>
          </div>

          <UFormField label="Descrição" help="opcional, até 1000 caracteres">
            <UTextarea v-model="draft.description" :rows="3" class="w-full" />
          </UFormField>

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="SLA (horas)" help="opcional, 1 a 720">
              <UInput v-model="draft.sla_hours" type="number" min="1" max="720" class="w-full" />
            </UFormField>
            <UFormField label="Ícone" required>
              <USelect v-model="draft.icon" :items="CATALOG_ICON_OPTIONS" class="w-full" />
            </UFormField>
            <UFormField label="Fila Znuny">
              <UInput v-model="draft.znuny_queue" class="w-full" />
            </UFormField>
            <UFormField label="Serviço Znuny">
              <UInput v-model="draft.znuny_service" class="w-full" />
            </UFormField>
            <UFormField label="Prioridade padrão">
              <UInput v-model="draft.default_priority" placeholder="ex.: 3 normal" class="w-full" />
            </UFormField>
            <UFormField label="Ordem" help="0 a 999">
              <UInput v-model.number="draft.sort_order" type="number" min="0" max="999" class="w-full" />
            </UFormField>
          </div>

          <UCheckbox v-model="draft.active" label="Ativo (visível na vitrine do portal)" />
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="submitting" @click="formOpen = false" />
        <UButton
          :label="editingId ? 'Salvar alterações' : 'Criar item'"
          color="primary"
          icon="i-lucide-check"
          :loading="submitting"
          @click="submit"
        />
      </template>
    </UModal>

    <!-- Modal excluir -->
    <UModal
      v-model:open="deleteOpen"
      title="Excluir item"
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-3">
          <UAlert
            color="error"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="Esta ação não pode ser desfeita."
          />
          <p class="text-sm text-default">
            Para confirmar, digite o nome do item:
            <span class="font-semibold text-highlighted">{{ deleteTarget?.name }}</span>
          </p>
          <UInput v-model="deleteConfirmText" placeholder="digite o nome aqui" class="w-full" />
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="deleting" @click="deleteOpen = false" />
        <UButton
          label="Excluir definitivamente"
          color="error"
          icon="i-lucide-trash-2"
          :loading="deleting"
          :disabled="!canConfirmDelete"
          @click="confirmDelete"
        />
      </template>
    </UModal>
  </div>
</template>
