<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'
import { deployStateColor, inciStateColor } from '~/components/asset/asset-labels'

// #1K fase 3 — Detalhe de ativo (CMDB). Read-only; 404 → "ativo não encontrado"
// (o backend devolve 404 anti-IDOR p/ CI de outro tenant). Botão primário abre
// um chamado já vinculado ao ativo (config_item_id) via query ?ativo=<id>.
definePageMeta({ middleware: 'auth' })

interface AssetDetail {
  znuny_config_item_id: number
  number: string
  class_: string
  name: string
  deploy_state: string | null
  inci_state: string | null
  customer_id: string | null
  attributes: Record<string, unknown> | null
}

const route = useRoute()
const id = computed(() => String(route.params.id))
const headers = useRequestHeaders(['cookie'])
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const { data: asset } = await useAsyncData(`asset-${id.value}`, () =>
  $fetch<AssetDetail | null>(`/api/portal/assets/${id.value}`, { headers }).catch(() => null))

// Linhas da tabela de atributos: campos fixos + o dicionário `attributes` (ex.:
// SerialNumber). Valores não-escalares são serializados de forma legível.
function fmtValue(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v)
  return JSON.stringify(v)
}
const attributeRows = computed(() => {
  const a = asset.value
  if (!a) return [] as { label: string, value: string }[]
  const rows: { label: string, value: string }[] = [
    { label: 'Número', value: a.number || '—' },
    { label: 'Classe', value: a.class_ || '—' },
  ]
  if (a.customer_id) rows.push({ label: 'Cliente', value: a.customer_id })
  for (const [k, v] of Object.entries(a.attributes ?? {})) {
    rows.push({ label: k, value: fmtValue(v) })
  }
  return rows
})

// Link "abrir chamado a partir do ativo" — extraído para teste de lógica pura.
function ticketFromAssetPath(assetId: string): string {
  return `/tickets/novo?ativo=${assetId}`
}
async function openTicket() {
  await navigateTo(ticketFromAssetPath(id.value))
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-8">
    <NuxtLink to="/ativos" class="mb-6 inline-flex items-center gap-1.5 text-sm text-muted transition hover:text-highlighted">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" /> Voltar para ativos
    </NuxtLink>

    <!-- 404 / falha amigável -->
    <UCard v-if="!asset" class="text-center">
      <div class="flex flex-col items-center gap-4 py-12">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-elevated text-dimmed">
          <UIcon name="i-lucide-search-x" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Ativo não encontrado</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            Este ativo não existe ou não pertence à sua empresa.
          </p>
        </div>
        <UButton to="/ativos" color="neutral" variant="subtle" icon="i-lucide-arrow-left" label="Ver todos os ativos" />
      </div>
    </UCard>

    <template v-else>
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <header class="mb-6 flex flex-wrap items-center gap-3">
        <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
          {{ asset.name || 'Ativo' }}
        </h1>
        <UBadge color="neutral" variant="subtle">{{ asset.class_ }}</UBadge>
        <UBadge
          v-if="asset.deploy_state"
          :color="deployStateColor(asset.deploy_state)"
          variant="soft"
        >
          {{ asset.deploy_state }}
        </UBadge>
        <UBadge
          v-if="asset.inci_state"
          :color="inciStateColor(asset.inci_state)"
          variant="soft"
        >
          {{ asset.inci_state }}
        </UBadge>
      </header>

      <UButton
        color="primary"
        size="lg"
        icon="i-lucide-life-buoy"
        label="Abrir chamado sobre este ativo"
        class="mb-6"
        @click="openTicket"
      />

      <UCard>
        <p class="mb-3 font-display text-sm font-semibold text-toned">Detalhes</p>
        <dl class="divide-y divide-default">
          <div
            v-for="row in attributeRows"
            :key="row.label"
            class="flex items-start justify-between gap-4 py-2.5 text-sm"
          >
            <dt class="text-muted">{{ row.label }}</dt>
            <dd class="text-right font-medium text-toned">{{ row.value }}</dd>
          </div>
        </dl>
      </UCard>
    </template>
  </div>
</template>
