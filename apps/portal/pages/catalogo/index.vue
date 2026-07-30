<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'
import { catalogIconName } from '~/components/catalog/catalog-icons'

// Spec #3 · V2 — Vitrine do catálogo de serviços. Qualquer papel autenticado
// acessa. "Solicitar" leva à abertura de chamado pré-preenchida
// (/tickets/novo?servico=<id>) — a página de novo chamado busca o item e
// decide sozinha se pré-preenche (id inválido/inativo não gera erro aqui,
// só na navegação seguinte).
definePageMeta({ middleware: 'auth' })

interface CatalogItem {
  id: string
  name: string
  category: string
  description: string | null
  sla_hours: number | null
  icon: string
}
interface CategoryCount { category: string, count: number }

const headers = useSidecarHeaders()
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const selectedCategory = ref('')

const { data: categories } = await useAsyncData('catalog-categories', () =>
  $fetch<CategoryCount[] | null>('/api/portal/catalog/categories', { headers }).catch(() => null))

const { data: items, pending, refresh } = await useAsyncData<CatalogItem[] | null>(
  'catalog-items',
  () => {
    const qs = selectedCategory.value ? `?category=${encodeURIComponent(selectedCategory.value)}` : ''
    return $fetch<CatalogItem[]>(`/api/portal/catalog/items${qs}`, { headers }).catch(() => null)
  },
  { watch: [selectedCategory] },
)

const loadFailed = computed(() => !pending.value && items.value === null)
const isEmpty = computed(() => !pending.value && Array.isArray(items.value) && items.value.length === 0)

function selectCategory(cat: string) {
  selectedCategory.value = selectedCategory.value === cat ? '' : cat
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-8">
    <header class="mb-6">
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Catálogo de Serviços
      </h1>
      <p class="mt-1 text-sm text-muted">
        Solicite um serviço padronizado e o chamado já nasce com os dados corretos.
      </p>
    </header>

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

    <!-- Loading -->
    <div v-if="pending" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="n in 6" :key="n" class="h-[150px] animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-4 py-10">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-error/10 text-error">
          <UIcon name="i-lucide-cloud-off" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar o catálogo</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            O catálogo de serviços está indisponível no momento. Tente novamente em instantes.
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
          <UIcon name="i-lucide-layout-grid" class="h-8 w-8" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Nenhum serviço disponível</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            {{ selectedCategory
              ? 'Nenhum serviço nesta categoria. Escolha outra ou veja todas.'
              : 'Ainda não há serviços publicados no catálogo. Abra um chamado normal se precisar de ajuda.' }}
          </p>
          <UButton to="/tickets/novo" color="neutral" variant="subtle" icon="i-lucide-ticket" label="Abrir chamado" class="mt-4" />
        </div>
      </div>
    </UCard>

    <!-- Grid -->
    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="item in items"
        :key="item.id"
        class="flex flex-col rounded-xl border border-default bg-default p-4"
      >
        <div class="mb-3 flex items-center gap-3">
          <span
            class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-white shadow-sm"
            :style="{ background: 'linear-gradient(135deg, var(--brand-primary), var(--brand-accent))' }"
          >
            <UIcon :name="catalogIconName(item.icon)" class="h-5 w-5" />
          </span>
          <div class="min-w-0">
            <p class="truncate font-display font-semibold text-highlighted">{{ item.name }}</p>
            <UBadge color="neutral" variant="subtle" size="xs">{{ item.category }}</UBadge>
          </div>
        </div>
        <p v-if="item.description" class="mb-3 line-clamp-3 flex-1 text-sm text-muted">{{ item.description }}</p>
        <div class="mt-auto flex items-center justify-between gap-2 pt-2">
          <UBadge v-if="item.sla_hours" color="info" variant="soft" size="sm" icon="i-lucide-clock">
            SLA {{ item.sla_hours }}h
          </UBadge>
          <span v-else />
          <UButton
            :to="`/tickets/novo?servico=${item.id}`"
            color="primary"
            size="sm"
            icon="i-lucide-send"
            label="Solicitar"
          />
        </div>
      </div>
    </div>
  </div>
</template>
