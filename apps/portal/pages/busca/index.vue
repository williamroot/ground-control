<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'
import type { SearchResults } from '#shared/search'
import { debounce, isSearchableQuery, SEARCH_DEBOUNCE_MS, searchSections, searchTotal } from '#shared/search'

// #3 V6 — busca federada (chamados/ativos/base de conhecimento/catálogo).
// Dispara a partir de 2 caracteres, debounce de 300ms. Cada item navega para
// o `path` que o backend devolve — usado AS-IS, sem concatenar nada (ver
// shared/search.ts).
definePageMeta({ middleware: 'auth' })

const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const query = ref('')
const results = ref<SearchResults | null>(null)
const pending = ref(false)
const loadFailed = ref(false)
const searched = ref(false)

async function runSearch(q: string) {
  if (!isSearchableQuery(q)) {
    pending.value = false
    loadFailed.value = false
    searched.value = false
    results.value = null
    return
  }
  pending.value = true
  loadFailed.value = false
  const res = await $fetch<SearchResults | null>('/api/portal/search', {
    query: { q: q.trim() },
  }).catch(() => null)
  pending.value = false
  searched.value = true
  if (res === null) {
    loadFailed.value = true
    results.value = null
    return
  }
  results.value = res
}

const debounced = debounce((q: string) => { void runSearch(q) }, SEARCH_DEBOUNCE_MS)
watch(query, q => debounced.run(q))
onBeforeUnmount(() => debounced.cancel())

const sections = computed(() => searchSections(results.value))
const total = computed(() => searchTotal(results.value))
const isInitial = computed(() => !isSearchableQuery(query.value) && !pending.value)
const isEmpty = computed(() => searched.value && !pending.value && !loadFailed.value && total.value === 0)
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-8">
    <header class="mb-6">
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Busca
      </h1>
    </header>

    <div class="relative mb-8">
      <UIcon name="i-lucide-search" class="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-dimmed" />
      <input
        v-model="query"
        type="search"
        autofocus
        placeholder="Buscar chamados, ativos, artigos, serviços…"
        class="w-full rounded-xl border border-default bg-default py-3 pl-11 pr-4 text-base text-default outline-none transition focus:border-[var(--brand-primary)]"
      >
    </div>

    <!-- Estado inicial -->
    <div v-if="isInitial" class="flex flex-col items-center gap-3 py-16 text-center text-muted">
      <UIcon name="i-lucide-search" class="h-10 w-10 text-dimmed" />
      <p>Digite para buscar…</p>
    </div>

    <!-- Loading -->
    <div v-else-if="pending" class="space-y-3">
      <div v-for="n in 3" :key="n" class="h-[60px] animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-4 py-10">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-error/10 text-error">
          <UIcon name="i-lucide-cloud-off" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível buscar</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            A busca está indisponível no momento. Tente novamente em instantes.
          </p>
        </div>
        <UButton color="neutral" variant="subtle" icon="i-lucide-rotate-cw" label="Tentar novamente" @click="runSearch(query)" />
      </div>
    </UCard>

    <!-- Sem resultado -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-4 py-12">
        <span class="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-muted text-dimmed">
          <UIcon name="i-lucide-search-x" class="h-8 w-8" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Nenhum resultado encontrado</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">Tente outros termos de busca.</p>
        </div>
      </div>
    </UCard>

    <!-- Resultados -->
    <div v-else class="space-y-6">
      <p class="text-sm text-muted">{{ total }} resultado{{ total === 1 ? '' : 's' }}</p>
      <section v-for="s in sections" :key="s.key">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-dimmed">
          {{ s.label }} ({{ s.items.length }})
        </h2>
        <ul class="space-y-2">
          <li v-for="item in s.items" :key="item.id">
            <NuxtLink
              :to="item.path"
              class="block rounded-xl border border-default bg-default px-4 py-3 transition hover:border-highlighted hover:shadow-sm"
            >
              <p class="font-medium text-highlighted">{{ item.title }}</p>
              <p v-if="item.subtitle" class="mt-0.5 text-sm text-muted">{{ item.subtitle }}</p>
            </NuxtLink>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
