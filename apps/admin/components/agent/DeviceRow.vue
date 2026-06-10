<script setup lang="ts">
// #1R-a — linha de dispositivo na tabela de Agentes. HTML nativo (sem U*/icon)
// p/ montar limpo no vitest (lição #1M..#1Q). Status em cor SEMÂNTICA (H8):
// active=success, pending=warning, offline=neutral, revoked=error. Aprovar só
// aparece em pending; revogar em active/offline; revoked não oferece ação.
import { computed } from 'vue'
import {
  type Device,
  deviceStatusColor,
  deviceStatusLabel,
  effectiveStatus,
  specsSummary,
} from '../../composables/useAgents'

const props = defineProps<{
  device: Device
  heartbeatInterval: number
}>()

const emit = defineEmits<{
  approve: [id: string]
  revoke: [id: string]
}>()

const eff = computed(() =>
  effectiveStatus(props.device.status, props.device.last_seen_at, props.heartbeatInterval),
)
const color = computed(() => deviceStatusColor(eff.value))
const label = computed(() => deviceStatusLabel(eff.value))
const summary = computed(() => specsSummary(props.device.specs))

// Map cor semântica → classes Tailwind do badge (sem depender de UBadge).
const BADGE: Record<string, string> = {
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  neutral: 'bg-elevated text-muted',
  error: 'bg-error/10 text-error',
}

function fmtLastSeen(iso: string | null): string {
  if (!iso) return 'nunca'
  return new Date(iso).toLocaleString('pt-BR')
}
</script>

<template>
  <tr data-testid="device-row" class="border-t border-default">
    <td class="px-4 py-3">
      <div class="font-medium text-highlighted">{{ device.hostname }}</div>
      <div class="font-mono text-xs text-dimmed">{{ device.fingerprint }}</div>
    </td>
    <td class="px-4 py-3 text-muted">{{ device.os || '—' }}</td>
    <td class="px-4 py-3 text-muted">{{ summary || '—' }}</td>
    <td class="px-4 py-3 text-muted">{{ fmtLastSeen(device.last_seen_at) }}</td>
    <td class="px-4 py-3">
      <span
        data-testid="device-status"
        :class="BADGE[color]"
        class="inline-flex rounded-full px-2 py-0.5 text-xs font-semibold"
      >{{ label }}</span>
    </td>
    <td class="px-4 py-3">
      <div class="flex justify-end gap-2">
        <button
          v-if="device.status === 'pending'"
          type="button"
          data-testid="approve"
          class="rounded-md bg-success/10 px-2.5 py-1 text-xs font-medium text-success hover:bg-success/20"
          @click="emit('approve', device.id)"
        >
          Aprovar
        </button>
        <button
          v-if="device.status === 'active'"
          type="button"
          data-testid="revoke"
          class="rounded-md bg-error/10 px-2.5 py-1 text-xs font-medium text-error hover:bg-error/20"
          @click="emit('revoke', device.id)"
        >
          Revogar
        </button>
      </div>
    </td>
  </tr>
</template>
