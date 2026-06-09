<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'
import { deployStateColor, inciStateColor } from '~/components/asset/asset-labels'

// #1K fase 3 — Lista de ativos (CMDB). Read-only: o backend escopa por tenant
// (CustomerID server-trusted). Estados explícitos: loading, vazio, erro (503).
// `null` = falha (proxy devolve null em não-200) → estado de erro. `[]` = vazio.
definePageMeta({ middleware: 'auth' })

interface AssetRow {
  znuny_config_item_id: number
  number: string
  class_: string
  name: string
  deploy_state: string | null
  inci_state: string | null
}

const headers = useRequestHeaders(['cookie'])
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const { data: assets, pending, refresh } = await useAsyncData('assets-list', () =>
  $fetch<AssetRow[] | null>('/api/portal/assets', { headers }).catch(() => null))

const loadFailed = computed(() => !pending.value && assets.value === null)
const isEmpty = computed(() => !pending.value && Array.isArray(assets.value) && assets.value.length === 0)
</script>

<template>
  <div class="mx-auto max-w-4xl px-5 py-8">
    <header class="mb-8">
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Ativos
      </h1>
      <p class="mt-1 text-sm text-muted">
        Equipamentos e serviços cadastrados da sua empresa.
      </p>
    </header>

    <!-- Loading -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 4" :key="n" class="h-[72px] animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro (sidecar/CMDB indisponível) -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-4 py-10">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-error/10 text-error">
          <UIcon name="i-lucide-cloud-off" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar os ativos</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            O inventário está indisponível no momento. Tente novamente em instantes.
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
          <UIcon name="i-lucide-server" class="h-8 w-8" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Nenhum ativo cadastrado</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            Quando equipamentos ou serviços forem cadastrados para a sua empresa, eles aparecerão aqui.
          </p>
        </div>
      </div>
    </UCard>

    <!-- Lista -->
    <ul v-else class="space-y-3">
      <li v-for="a in assets ?? []" :key="a.znuny_config_item_id">
        <NuxtLink
          :to="`/ativos/${a.znuny_config_item_id}`"
          class="block rounded-xl border border-default bg-default px-4 py-3.5 transition hover:border-highlighted hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <UBadge color="neutral" variant="subtle" size="sm">{{ a.class_ }}</UBadge>
                <span class="font-mono text-xs text-dimmed">#{{ a.number }}</span>
              </div>
              <p class="mt-1 truncate font-medium text-highlighted">{{ a.name || 'Sem nome' }}</p>
            </div>
            <UIcon name="i-lucide-chevron-right" class="mt-1 h-5 w-5 shrink-0 text-dimmed" />
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <UBadge
              v-if="a.deploy_state"
              :color="deployStateColor(a.deploy_state)"
              variant="soft"
              size="sm"
            >
              <UIcon name="i-lucide-rocket" class="h-3 w-3" />
              {{ a.deploy_state }}
            </UBadge>
            <UBadge
              v-if="a.inci_state"
              :color="inciStateColor(a.inci_state)"
              variant="soft"
              size="sm"
            >
              <UIcon name="i-lucide-activity" class="h-3 w-3" />
              {{ a.inci_state }}
            </UBadge>
          </div>
        </NuxtLink>
      </li>
    </ul>
  </div>
</template>
