<script setup lang="ts">
// Linha da árvore de Serviços do Znuny (Spec #4). HTML nativo (sem U*) para
// montar limpo no vitest (lição #1M..#1Q). A indentação vem de `depth`
// (calculado pela composable useServiceTree a partir do ParentID); o nome
// exibido é só o nível atual (leafName), não o "Pai::Filho" inteiro.
import { computed } from 'vue'
import type { ServiceRow } from '../../composables/useServiceTree'

const props = defineProps<{
  row: ServiceRow
  leafName: string
  depth: number
  validLabel: string
}>()

defineEmits<{
  edit: []
  invalidate: []
}>()

const isValid = computed(() => props.row.ValidID === '1')
</script>

<template>
  <tr data-testid="service-row" :data-service-id="row.id" class="border-t border-default">
    <td class="px-4 py-2.5">
      <span :style="{ paddingLeft: `${depth * 1.25}rem` }" class="inline-flex items-center gap-1.5">
        <span v-if="depth > 0" class="text-dimmed" aria-hidden="true">└</span>
        <span data-testid="service-leaf-name" class="font-medium text-highlighted">{{ leafName }}</span>
      </span>
    </td>
    <td class="px-4 py-2.5 text-muted">{{ row.Comment || '—' }}</td>
    <td class="px-4 py-2.5">
      <span
        data-testid="service-status"
        :class="isValid ? 'text-success' : 'text-muted'"
        class="text-xs font-medium"
      >{{ validLabel }}</span>
    </td>
    <td class="px-4 py-2.5 text-right">
      <button
        type="button"
        data-testid="service-edit"
        class="rounded-md px-2 py-1 text-sm text-muted hover:text-default"
        @click="$emit('edit')"
      >
        Editar
      </button>
      <button
        v-if="isValid"
        type="button"
        data-testid="service-invalidate"
        class="rounded-md px-2 py-1 text-sm text-muted hover:text-error"
        @click="$emit('invalidate')"
      >
        Invalidar
      </button>
    </td>
  </tr>
</template>
