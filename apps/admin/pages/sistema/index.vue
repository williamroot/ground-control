<script setup lang="ts">
// Saúde do sistema (Spec #3, V6) — cartões por sonda (banco, Znuny/GI, worker
// de consumo, IA, Asaas). Formatação pura em composables/useSystemHealth.ts.
// Uma sonda vermelha não derruba a tela; só o endpoint inteiro falhando vira
// card de erro (nunca tela branca).
import {
  formatLagSeconds,
  formatLatency,
  HEALTH_CARDS,
  probeStatus,
  probeStatusColor,
  probeStatusLabel,
  type SystemHealth,
} from '../../composables/useSystemHealth'

definePageMeta({ middleware: 'admin-auth' })

const headers = useRequestHeaders(['cookie'])

const { data: health, pending, refresh } = await useAsyncData<SystemHealth | null>('sistema-health', () =>
  $fetch<SystemHealth | null>('/api/admin/system/health', { headers }).catch(() => null))

const loadFailed = computed(() => !pending.value && health.value === null)

const lastChecked = ref<Date | null>(null)
onMounted(() => { lastChecked.value = new Date() })

const checking = ref(false)
async function checkNow() {
  checking.value = true
  try {
    await refresh()
    lastChecked.value = new Date()
  }
  finally {
    checking.value = false
  }
}

const lastCheckedLabel = computed(() =>
  lastChecked.value ? lastChecked.value.toLocaleString('pt-BR') : '—')
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <header class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Saúde do sistema
        </h1>
        <p class="mt-1 text-sm text-muted">
          Estado das dependências do sidecar. Sondas com timeout curto — uma falha isolada não derruba as demais.
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="health" class="text-xs text-muted">
          versão {{ health.version }} · verificado às {{ lastCheckedLabel }}
        </span>
        <UButton
          variant="soft"
          color="primary"
          icon="i-lucide-refresh-cw"
          :loading="checking"
          @click="checkNow"
        >
          Verificar novamente
        </UButton>
      </div>
    </header>

    <div v-if="pending" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="n in 5" :key="n" class="h-28 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível verificar a saúde do sistema</p>
        <p class="max-w-sm text-sm text-muted">
          O endpoint de saúde não respondeu. O sidecar pode estar fora do ar.
        </p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="checkNow">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <div v-else-if="health" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <UCard v-for="card in HEALTH_CARDS" :key="card.key" :ui="{ body: 'space-y-2' }">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <UIcon :name="card.icon" class="h-4 w-4 text-muted" />
            <p class="font-display text-sm font-bold text-highlighted">{{ card.label }}</p>
          </div>
          <span
            class="inline-flex h-2.5 w-2.5 rounded-full"
            :class="{
              'bg-success': probeStatus(health[card.key]) === 'ok',
              'bg-error': probeStatus(health[card.key]) === 'error',
              'bg-muted': probeStatus(health[card.key]) === 'disabled',
              'bg-warning': probeStatus(health[card.key]) === 'unknown',
            }"
          />
        </div>
        <UBadge :color="probeStatusColor(probeStatus(health[card.key]))" variant="soft" size="sm">
          {{ probeStatusLabel(probeStatus(health[card.key])) }}
        </UBadge>
        <p v-if="formatLatency(health[card.key].latency_ms)" class="text-xs text-muted">
          latência: {{ formatLatency(health[card.key].latency_ms) }}
        </p>
        <p v-if="formatLagSeconds(health[card.key].lag_seconds)" class="text-xs text-muted">
          {{ formatLagSeconds(health[card.key].lag_seconds) }}
        </p>
        <p v-if="health[card.key].message" class="text-xs text-error">
          {{ health[card.key].message }}
        </p>
      </UCard>
    </div>
  </div>
</template>
