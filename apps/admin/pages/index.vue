<script setup lang="ts">
import { statusColor, statusLabel } from '#shared/contracts'

definePageMeta({ middleware: 'admin-auth' })

interface TenantSummary {
  id: string
  trade_name: string
  subdomain: string
  contract_count: number
  status: string
}

const headers = useRequestHeaders(['cookie'])
const { data: tenants } = await useAsyncData('admin-tenants', () =>
  $fetch<TenantSummary[]>('/api/admin/tenants', { headers })
    .catch(() => [] as TenantSummary[]))
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <header class="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Clientes
        </h1>
        <p class="mt-1 text-sm text-muted">
          Tenants provisionados no Gerti. Selecione um cliente para ver detalhes e contratos.
        </p>
      </div>
      <UButton to="/clientes/novo" color="primary" icon="i-lucide-plus" size="md">
        Novo cliente
      </UButton>
    </header>

    <UCard v-if="!tenants || tenants.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-12">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary text-white">
          <UIcon name="i-lucide-building-2" class="h-6 w-6" />
        </span>
        <p class="font-display text-lg font-semibold text-highlighted">
          Nenhum cliente ainda
        </p>
        <p class="max-w-sm text-sm text-muted">
          Comece o onboarding do primeiro cliente para provisioná-lo no Gerti.
        </p>
        <UButton to="/clientes/novo" color="primary" icon="i-lucide-plus" class="mt-1">
          Novo cliente
        </UButton>
      </div>
    </UCard>

    <div v-else class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      <NuxtLink
        v-for="t in tenants"
        :key="t.id"
        :to="`/clientes/${t.id}`"
        class="block"
      >
        <UCard class="h-full transition hover:shadow-md" :ui="{ body: 'space-y-3' }">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="truncate font-display text-base font-bold tracking-tight text-highlighted">
                {{ t.trade_name }}
              </p>
              <p class="mt-0.5 truncate text-xs text-muted">
                {{ t.subdomain }}
              </p>
            </div>
            <UBadge :color="statusColor(t.status)" variant="soft" size="sm">
              {{ statusLabel(t.status) }}
            </UBadge>
          </div>
          <div class="flex items-center gap-1.5 text-xs text-muted">
            <UIcon name="i-lucide-file-text" class="h-3.5 w-3.5" />
            <span>{{ t.contract_count }} contrato(s)</span>
          </div>
        </UCard>
      </NuxtLink>
    </div>
  </div>
</template>
