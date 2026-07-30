<script setup lang="ts">
// Busca federada do staff (Spec #3, V6) — debounce 300ms a partir de 2
// caracteres. Seções só aparecem quando têm resultado. `path` usado como veio
// do backend, sem concatenar nada (lógica pura em composables/useStaffSearch.ts).
import {
  hasAnyResult,
  MIN_QUERY_LENGTH,
  SEARCH_DEBOUNCE_MS,
  SEARCH_SECTIONS,
  shouldSearch,
  type StaffSearchResponse,
} from '../../composables/useStaffSearch'

definePageMeta({ middleware: 'admin-auth' })

const headers = useRequestHeaders(['cookie'])

const q = ref('')
const debouncedQ = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
watch(q, (value) => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { debouncedQ.value = value }, SEARCH_DEBOUNCE_MS)
})

const active = computed(() => shouldSearch(debouncedQ.value))

const { data: results, pending } = await useAsyncData<StaffSearchResponse | null>(
  'busca-staff',
  () => {
    if (!active.value) return Promise.resolve(null)
    return $fetch<StaffSearchResponse>('/api/admin/search', {
      headers,
      query: { q: debouncedQ.value.trim() },
    }).catch(() => null)
  },
  { watch: [debouncedQ] },
)

const isSearching = computed(() => active.value && pending.value)
const loadFailed = computed(() => active.value && !pending.value && results.value === null)
const noResults = computed(() =>
  active.value && !pending.value && results.value !== null && !hasAnyResult(results.value))
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-10">
    <header class="mb-6">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Busca
      </h1>
      <p class="mt-1 text-sm text-muted">
        Clientes, chamados e base de conhecimento — tudo em um lugar só.
      </p>
    </header>

    <UInput
      v-model="q"
      autofocus
      size="xl"
      icon="i-lucide-search"
      placeholder="Digite pelo menos 2 caracteres…"
      class="w-full"
    />

    <div class="mt-8">
      <p v-if="!active" class="text-sm text-muted">
        Digite ao menos {{ MIN_QUERY_LENGTH }} caracteres para buscar.
      </p>

      <div v-else-if="isSearching" class="space-y-3">
        <div v-for="n in 3" :key="n" class="h-12 animate-pulse rounded-lg border border-default bg-elevated" />
      </div>

      <UCard v-else-if="loadFailed" class="text-center">
        <div class="flex flex-col items-center gap-3 py-8">
          <UIcon name="i-lucide-alert-triangle" class="h-8 w-8 text-error" />
          <p class="text-sm text-muted">Falha ao buscar. Tente novamente.</p>
        </div>
      </UCard>

      <UCard v-else-if="noResults" class="text-center">
        <div class="flex flex-col items-center gap-3 py-8">
          <UIcon name="i-lucide-search-x" class="h-8 w-8 text-muted" />
          <p class="text-sm text-muted">Nenhum resultado para "{{ debouncedQ }}".</p>
        </div>
      </UCard>

      <div v-else-if="results" class="space-y-6">
        <section v-for="section in SEARCH_SECTIONS" :key="section.key">
          <template v-if="(results[section.key]?.length ?? 0) > 0">
            <h2 class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-dimmed">
              <UIcon :name="section.icon" class="h-3.5 w-3.5" />
              {{ section.label }}
            </h2>
            <div class="overflow-hidden rounded-lg border border-default">
              <NuxtLink
                v-for="item in results[section.key]"
                :key="item.id"
                :to="item.path"
                class="flex flex-col gap-0.5 border-b border-default px-4 py-3 last:border-b-0 hover:bg-elevated"
              >
                <span class="text-sm font-medium text-default">{{ item.title }}</span>
                <span v-if="item.subtitle" class="text-xs text-muted">{{ item.subtitle }}</span>
              </NuxtLink>
            </div>
          </template>
        </section>
      </div>
    </div>
  </div>
</template>
