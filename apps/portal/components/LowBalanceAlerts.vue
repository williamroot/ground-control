<script setup lang="ts">
interface Alert {
  contract_id: string, code: string, type: string, kind: string
  remaining: number, consumed_percent: number | null, severity: 'warning' | 'critical'
}
defineProps<{ alerts: Alert[] }>()

// Semantic colors — FIXED, never --brand-primary (an alert must read as an
// alert in ANY tenant brand — Spec §4.3.2 / H8).
// Tokens semânticos do Nuxt UI (warning/error) — adaptam light/dark sozinhos e
// continuam FIXOS, nunca --brand-primary (um alerta deve ler como alerta em
// qualquer marca — Spec §4.3.2 / H8).
const META: Record<string, { ring: string, text: string, icon: string, label: string }> = {
  warning: { ring: 'border-warning/40 bg-warning/10', text: 'text-warning', icon: 'i-lucide-alert-triangle', label: 'Saldo baixo' },
  critical: { ring: 'border-error/40 bg-error/10', text: 'text-error', icon: 'i-lucide-alert-octagon', label: 'Saldo esgotado' },
}
</script>

<template>
  <div v-if="alerts.length" class="mb-6 space-y-2">
    <NuxtLink
      v-for="a in alerts"
      :key="a.contract_id"
      :to="`/contratos/${a.contract_id}`"
      class="flex items-center gap-3 rounded-xl border px-4 py-3 transition hover:shadow-sm"
      :class="META[a.severity].ring"
    >
      <UIcon :name="META[a.severity].icon" class="h-5 w-5" :class="META[a.severity].text" />
      <div class="min-w-0">
        <p class="text-sm font-semibold" :class="META[a.severity].text">
          {{ META[a.severity].label }} — {{ a.code }}
        </p>
        <p class="text-xs text-muted">
          Restam {{ a.remaining.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) }}
          {{ a.kind === 'hours' ? 'h' : a.kind === 'brl' ? 'em crédito' : 'serviços' }}
        </p>
      </div>
      <UIcon name="i-lucide-chevron-right" class="ml-auto h-4 w-4 text-dimmed" />
    </NuxtLink>
  </div>
</template>
