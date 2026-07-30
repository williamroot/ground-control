<script setup lang="ts">
// Base de Conhecimento — CRUD do console para o cliente selecionado (Spec #3,
// V1). Cross-tenant por natureza: o nome do cliente fica sempre visível para o
// operador não editar/excluir artigo do tenant errado (H2 do console).
import {
  buildKbArticlePayload,
  emptyKbDraft,
  kbDraftFromDetail,
  KB_STATUS_OPTIONS,
  KB_VISIBILITY_OPTIONS,
  kbStatusColor,
  kbStatusLabel,
  kbVisibilityLabel,
  parseTagsInput,
  tagsToInput,
  validateKbArticle,
  type KbArticleDetail,
  type KbArticleDraft,
  type KbArticleListItem,
} from '../../../composables/useKbArticle'

definePageMeta({ middleware: 'admin-auth' })

interface TenantBrief { id: string, trade_name: string }
interface ArticlesResponse { items: KbArticleListItem[], total: number, limit: number, offset: number }

const route = useRoute()
const tenantId = route.params.id as string
const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const { data: tenant } = await useAsyncData(`admin-tenant-brief-kb-${tenantId}`, () =>
  $fetch<TenantBrief | null>(`/api/admin/tenants/${tenantId}`, { headers }).catch(() => null))

// --- Lista + filtros -------------------------------------------------------
const q = ref('')
const statusFilter = ref('')
const categoryFilter = ref('')

const { data: articlesRes, pending, refresh } = await useAsyncData(
  `admin-kb-articles-${tenantId}`,
  () => {
    const params = new URLSearchParams()
    if (q.value.trim()) params.set('q', q.value.trim())
    if (statusFilter.value) params.set('status', statusFilter.value)
    if (categoryFilter.value.trim()) params.set('category', categoryFilter.value.trim())
    const qs = params.toString()
    return $fetch<ArticlesResponse | null>(
      `/api/admin/tenants/${tenantId}/kb/articles${qs ? `?${qs}` : ''}`,
      { headers },
    ).catch(() => null)
  },
  { watch: [statusFilter, categoryFilter] },
)

const loadFailed = computed(() => !pending.value && articlesRes.value === null)
const articles = computed(() => articlesRes.value?.items ?? [])
const isEmpty = computed(() => !pending.value && !loadFailed.value && articles.value.length === 0)

const statusFilterOptions = [{ label: 'Todos os status', value: '' }, ...KB_STATUS_OPTIONS]

// --- Formulário criar/editar -------------------------------------------------
const formOpen = ref(false)
const editingId = ref<string | null>(null)
const draft = reactive<KbArticleDraft>(emptyKbDraft())
const tagsInput = ref('')
const formError = ref('')
const submitting = ref(false)
const loadingDetail = ref(false)

function openCreate() {
  editingId.value = null
  Object.assign(draft, emptyKbDraft())
  tagsInput.value = ''
  formError.value = ''
  formOpen.value = true
}

async function openEdit(row: KbArticleListItem) {
  formError.value = ''
  loadingDetail.value = true
  formOpen.value = true
  editingId.value = row.id
  try {
    const detail = await $fetch<KbArticleDetail | null>(
      `/api/admin/tenants/${tenantId}/kb/articles/${row.id}`,
    ).catch(() => null)
    if (!detail) {
      formError.value = 'Não foi possível carregar o artigo. Tente novamente.'
      Object.assign(draft, emptyKbDraft())
      tagsInput.value = ''
      return
    }
    Object.assign(draft, kbDraftFromDetail(detail))
    tagsInput.value = tagsToInput(detail.tags)
  }
  finally {
    loadingDetail.value = false
  }
}

async function submit() {
  formError.value = ''
  const tags = parseTagsInput(tagsInput.value)
  const draftWithTags = { ...draft, tags }
  const errors = validateKbArticle(draftWithTags)
  if (errors.length) {
    formError.value = errors[0]!
    return
  }

  submitting.value = true
  try {
    const payload = buildKbArticlePayload(draftWithTags)
    if (editingId.value) {
      await $fetch(`/api/admin/tenants/${tenantId}/kb/articles/${editingId.value}`, {
        method: 'PUT',
        body: payload,
      })
      toast.add({ title: 'Artigo atualizado', color: 'success' })
    }
    else {
      await $fetch(`/api/admin/tenants/${tenantId}/kb/articles`, {
        method: 'POST',
        body: payload,
      })
      toast.add({ title: 'Artigo criado', color: 'success' })
    }
    formOpen.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    formError.value
      = err.statusCode === 422
        ? (err.data?.detail || 'Dados inválidos. Confira os campos destacados.')
        : (err.data?.detail || 'Falha ao salvar o artigo. Tente novamente.')
  }
  finally {
    submitting.value = false
  }
}

// --- Exclusão com confirmação -----------------------------------------------
const deleteTarget = ref<KbArticleListItem | null>(null)
const deleteConfirmText = ref('')
const deleteOpen = ref(false)
const deleting = ref(false)

function openDelete(row: KbArticleListItem) {
  deleteTarget.value = row
  deleteConfirmText.value = ''
  deleteOpen.value = true
}

const canConfirmDelete = computed(() =>
  !!deleteTarget.value && deleteConfirmText.value.trim() === deleteTarget.value.title)

async function confirmDelete() {
  if (!deleteTarget.value || !canConfirmDelete.value) return
  deleting.value = true
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/kb/articles/${deleteTarget.value.id}`, {
      method: 'DELETE',
    })
    toast.add({ title: 'Artigo excluído', color: 'neutral' })
    deleteOpen.value = false
    await refresh()
  }
  catch {
    toast.add({ title: 'Falha ao excluir o artigo', color: 'error' })
  }
  finally {
    deleting.value = false
  }
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR')
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
          Base de Conhecimento
        </h1>
        <p class="mt-1 text-sm text-muted">
          Cliente: <span class="font-semibold text-default">{{ tenant?.trade_name ?? tenantId }}</span>
        </p>
      </div>
      <UButton color="primary" icon="i-lucide-plus" @click="openCreate">
        Novo artigo
      </UButton>
    </header>

    <!-- Filtros -->
    <div class="mb-6 flex flex-wrap items-end gap-3">
      <UFormField label="Buscar" class="min-w-[220px] flex-1">
        <UInput v-model="q" placeholder="título, resumo ou conteúdo" class="w-full" @keyup.enter="refresh()" />
      </UFormField>
      <UFormField label="Status">
        <USelect v-model="statusFilter" :items="statusFilterOptions" class="w-44" />
      </UFormField>
      <UFormField label="Categoria">
        <UInput v-model="categoryFilter" placeholder="ex.: contas" class="w-40" />
      </UFormField>
      <UButton variant="soft" color="neutral" icon="i-lucide-search" @click="refresh()">
        Buscar
      </UButton>
    </div>

    <!-- Loading -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 3" :key="n" class="h-16 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar os artigos</p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refresh()">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <!-- Vazio -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-book-open" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nenhum artigo ainda</p>
        <p class="text-sm text-muted">Crie o primeiro artigo da base de conhecimento deste cliente.</p>
        <UButton color="primary" icon="i-lucide-plus" class="mt-1" @click="openCreate">
          Novo artigo
        </UButton>
      </div>
    </UCard>

    <!-- Lista -->
    <div v-else class="overflow-hidden rounded-xl border border-default">
      <table class="w-full text-sm">
        <thead class="bg-elevated text-left text-xs uppercase text-muted">
          <tr>
            <th class="px-4 py-2.5">Título</th>
            <th class="px-4 py-2.5">Categoria</th>
            <th class="px-4 py-2.5">Visibilidade</th>
            <th class="px-4 py-2.5">Status</th>
            <th class="px-4 py-2.5 text-right">Views</th>
            <th class="px-4 py-2.5">Atualizado</th>
            <th class="px-4 py-2.5 text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in articles" :key="a.id" class="border-t border-default">
            <td class="px-4 py-3">
              <p class="font-semibold text-highlighted">{{ a.title }}</p>
              <p v-if="a.tags.length" class="mt-1 flex flex-wrap gap-1">
                <UBadge v-for="t in a.tags" :key="t" color="neutral" variant="subtle" size="xs">{{ t }}</UBadge>
              </p>
            </td>
            <td class="px-4 py-3 text-muted">{{ a.category }}</td>
            <td class="px-4 py-3 text-muted">{{ kbVisibilityLabel(a.visibility) }}</td>
            <td class="px-4 py-3">
              <UBadge :color="kbStatusColor(a.status)" variant="soft" size="sm">
                {{ kbStatusLabel(a.status) }}
              </UBadge>
            </td>
            <td class="px-4 py-3 text-right text-muted">{{ a.views }}</td>
            <td class="px-4 py-3 text-muted">{{ fmtDate(a.updated_at) }}</td>
            <td class="px-4 py-3">
              <div class="flex justify-end gap-2">
                <UButton size="xs" color="neutral" variant="soft" icon="i-lucide-pencil" @click="openEdit(a)">
                  Editar
                </UButton>
                <UButton size="xs" color="error" variant="soft" icon="i-lucide-trash-2" @click="openDelete(a)">
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
      :title="editingId ? 'Editar artigo' : 'Novo artigo'"
      :description="`Cliente: ${tenant?.trade_name ?? tenantId}`"
      :ui="{ content: 'max-w-2xl', footer: 'justify-end' }"
    >
      <template #body>
        <div v-if="loadingDetail" class="flex justify-center py-10">
          <UIcon name="i-lucide-loader-2" class="h-6 w-6 animate-spin text-muted" />
        </div>
        <div v-else class="space-y-4">
          <UAlert v-if="formError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="formError" />

          <UFormField label="Título" required>
            <UInput v-model="draft.title" placeholder="Como resetar a senha do e-mail" class="w-full" />
          </UFormField>

          <UFormField label="Resumo" help="Aparece na lista do portal (opcional, até 500 caracteres).">
            <UTextarea v-model="draft.summary" :rows="2" class="w-full" />
          </UFormField>

          <UFormField label="Conteúdo (Markdown)" required>
            <UTextarea v-model="draft.body_markdown" :rows="10" class="w-full font-mono text-sm" />
          </UFormField>

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Categoria" required>
              <UInput v-model="draft.category" placeholder="ex.: contas" class="w-full" />
            </UFormField>
            <UFormField label="Tags" help="separadas por vírgula, até 10, normalizadas em minúsculas">
              <UInput v-model="tagsInput" placeholder="vpn, e-mail, senha" class="w-full" />
            </UFormField>
            <UFormField label="Visibilidade" required>
              <USelect v-model="draft.visibility" :items="KB_VISIBILITY_OPTIONS" class="w-full" />
            </UFormField>
            <UFormField label="Status" required>
              <USelect v-model="draft.status" :items="KB_STATUS_OPTIONS" class="w-full" />
            </UFormField>
          </div>
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="submitting" @click="formOpen = false" />
        <UButton
          :label="editingId ? 'Salvar alterações' : 'Criar artigo'"
          color="primary"
          icon="i-lucide-check"
          :loading="submitting"
          :disabled="loadingDetail"
          @click="submit"
        />
      </template>
    </UModal>

    <!-- Modal excluir -->
    <UModal
      v-model:open="deleteOpen"
      title="Excluir artigo"
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
            Para confirmar, digite o título do artigo:
            <span class="font-semibold text-highlighted">{{ deleteTarget?.title }}</span>
          </p>
          <UInput v-model="deleteConfirmText" placeholder="digite o título aqui" class="w-full" />
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
