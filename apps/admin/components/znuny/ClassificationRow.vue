<script setup lang="ts">
// Linha de lista das três abas de Classificação (Tipos/Estados/Prioridades,
// Spec #4). HTML nativo (sem U*) p/ montar limpo no vitest (lição #1M..#1Q).
// Reusada pelas três abas; colunas extras (Comentário/Tipo de estado, só em
// Estados) entram pelo slot default.
import { computed } from 'vue'

const props = defineProps<{
  name: string
  validId: string
  validLabel: string
}>()

defineEmits<{
  edit: []
  invalidate: []
}>()

const isValid = computed(() => props.validId === '1')
</script>

<template>
  <tr data-testid="classification-row" class="border-t border-default">
    <td class="px-4 py-2.5 font-medium text-highlighted">{{ name }}</td>
    <slot />
    <td class="px-4 py-2.5">
      <span
        data-testid="classification-status"
        :class="isValid ? 'text-success' : 'text-muted'"
        class="text-xs font-medium"
      >{{ validLabel }}</span>
    </td>
    <td class="px-4 py-2.5 text-right">
      <button
        type="button"
        data-testid="classification-edit"
        class="rounded-md px-2 py-1 text-sm text-muted hover:text-default"
        @click="$emit('edit')"
      >
        Editar
      </button>
      <button
        v-if="isValid"
        type="button"
        data-testid="classification-invalidate"
        class="rounded-md px-2 py-1 text-sm text-muted hover:text-error"
        @click="$emit('invalidate')"
      >
        Invalidar
      </button>
    </td>
  </tr>
</template>
