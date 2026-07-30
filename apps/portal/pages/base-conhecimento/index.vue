<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

// Spec #3 · V1 — Base de Conhecimento (grid + busca + categorias). Qualquer
// papel autenticado acessa (não é admin-only). `null` = falha do proxy →
// estado de erro. `items: []` = vazio (sem resultado para o filtro atual).
definePageMeta({ middleware: 'auth' })

interface ArticleRow {
  id: string
  slug: string
  title: string
  summary: string | null
  category: string
  tags: string[]
  views: number
  updated_at: string
}
interface ArticleList { items: ArticleRow[], total: number, limit: number, offset: number }
interface CategoryCount { category: string, count: number }

const headers = useSidecarHeaders()
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const searchInput = ref('')
const q = ref('') // debounced
const selectedCategory = ref('')

let debounceTimer: ReturnType<typeof setTimeout> | undefined
watch(searchInput, (v) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { q.value = v.trim() }, 300)
})

const { data: categories } = await useAsyncData('kb-categories', () =>
  $fetch<CategoryCount[] | null>('/api/portal/kb/categories', { headers }).catch(() => null))

const { data: list, pending, refresh } = await useAsyncData<ArticleList | null>(
  'kb-articles',
  () => {
    const params = new URLSearchParams()
    if (q.value) params.set('q', q.value)
    if (selectedCategory.value) params.set('category', selectedCategory.value)
    const qs = params.toString()
    return $fetch<ArticleList>(`/api/portal/kb/articles${qs ? `?${qs}` : ''}`, { headers }).catch(() => null)
  },
  { watch: [q, selectedCategory] },
)

const articles = computed(() => list.value?.items ?? [])
const loadFailed = computed(() => !pending.value && list.value === null)
const isEmpty = computed(() => !pending.value && list.value !== null && articles.value.length === 0)

function selectCategory(cat: string) {
  selectedCategory.value = selectedCategory.value === cat ? '' : cat
}
function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR')
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-8">
    <header class="mb-6">
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Base de Conhecimento
      </h1>
      <p class="mt-1 text-sm text-muted">
        Artigos e guias para resolver dúvidas comuns sem precisar abrir um chamado.
      </p>
    </header>

    <div class="mb-4">
      <UInput
        v-model="searchInput"
        icon="i-lucide-search"
        size="lg"
        placeholder="Buscar artigos…"
        class="w-full sm:max-w-md"
        aria-label="Buscar artigos da base de conhecimento"
      />
    </div>

    <div v-if="categories && categories.length" class="mb-6 flex flex-wrap gap-2">
      <UButton
        size="sm"
        :color="selectedCategory === '' ? 'primary' : 'neutral'"
        :variant="selectedCategory === '' ? 'solid' : 'subtle'"
        label="Todas"
        @click="selectCategory('')"
      />
      <UButton
        v-for="c in categories"
        :key="c.category"
        size="sm"
        :color="selectedCategory === c.category ? 'primary' : 'neutral'"
        :variant="selectedCategory === c.category ? 'solid' : 'subtle'"
        :label="`${c.category} (${c.count})`"
        @click="selectCategory(c.category)"
      />
    </div>

    <p v-if="!pending && list" class="mb-4 text-sm text-muted">
      {{ articles.length }} {{ articles.length === 1 ? 'artigo encontrado' : 'artigos encontrados' }}
    </p>

    <!-- Loading -->
    <div v-if="pending" class="grid gap-4 sm:grid-cols-2">
      <div v-for="n in 4" :key="n" class="h-[120px] animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-4 py-10">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-error/10 text-error">
          <UIcon name="i-lucide-cloud-off" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar os artigos</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            A base de conhecimento está indisponível no momento. Tente novamente em instantes.
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
          <UIcon name="i-lucide-book-open" class="h-8 w-8" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Nenhum artigo encontrado</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            {{ q || selectedCategory
              ? 'Tente ajustar a busca ou escolher outra categoria.'
              : 'Ainda não há artigos publicados na base de conhecimento.' }}
          </p>
        </div>
      </div>
    </UCard>

    <!-- Grid -->
    <div v-else class="grid gap-4 sm:grid-cols-2">
      <NuxtLink
        v-for="a in articles"
        :key="a.id"
        :to="`/base-conhecimento/${a.slug}`"
        class="block rounded-xl border border-default bg-default p-4 transition hover:border-highlighted hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
      >
        <div class="mb-2 flex items-center justify-between gap-2">
          <UBadge color="neutral" variant="subtle" size="sm">{{ a.category }}</UBadge>
          <span class="inline-flex items-center gap-1 text-xs text-dimmed">
            <UIcon name="i-lucide-eye" class="h-3.5 w-3.5" />{{ a.views }}
          </span>
        </div>
        <p class="font-display font-semibold text-highlighted">{{ a.title }}</p>
        <p v-if="a.summary" class="mt-1 line-clamp-2 text-sm text-muted">{{ a.summary }}</p>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <UBadge v-for="t in a.tags.slice(0, 3)" :key="t" color="neutral" variant="outline" size="xs">{{ t }}</UBadge>
          <span class="ml-auto text-xs text-dimmed">Atualizado {{ fmtDate(a.updated_at) }}</span>
        </div>
      </NuxtLink>
    </div>
  </div>
</template>
