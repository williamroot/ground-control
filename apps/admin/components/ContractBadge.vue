<script setup lang="ts">
import { typeLabel } from '#shared/contracts'

// Vínculo de contrato de um ticket (#1J fase 3). Verde quando há contrato;
// âmbar "⚠ sem contrato" quando null — sinal claro de que o tempo lançado
// não terá onde debitar. NUNCA usa a cor de marca (reservada à navegação).
defineProps<{
  contract: { code: string, type: string } | null
}>()
</script>

<template>
  <UBadge
    v-if="contract"
    color="success"
    variant="soft"
    size="sm"
    class="gap-1.5"
  >
    <UIcon name="i-lucide-link" class="h-3.5 w-3.5" />
    <span class="font-medium">{{ contract.code }}</span>
    <span class="opacity-70">· {{ typeLabel(contract.type) }}</span>
  </UBadge>
  <UBadge
    v-else
    color="warning"
    variant="soft"
    size="sm"
    class="gap-1.5"
  >
    <UIcon name="i-lucide-triangle-alert" class="h-3.5 w-3.5" />
    sem contrato
  </UBadge>
</template>
