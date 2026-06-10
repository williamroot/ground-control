<script setup lang="ts">
// Linha de condição do editor de regras (#1Q). HTML nativo (sem U*/@nuxt/icon)
// p/ montar limpo no vitest (lição #1M..#1P). Emite o objeto {field,op,value}
// a cada mudança; o pai mantém a lista.
import type { RuleCondition } from '../../composables/useAutomationRule'

const props = defineProps<{
  modelValue: RuleCondition
  fields: string[]
  ops: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: RuleCondition]
  'remove': []
}>()

function patch(part: Partial<RuleCondition>) {
  emit('update:modelValue', { ...props.modelValue, ...part })
}
</script>

<template>
  <div data-testid="condition-row" class="flex flex-wrap items-center gap-2">
    <select
      data-testid="condition-field"
      :value="modelValue.field"
      class="rounded-md border border-default bg-default px-2 py-1.5 text-sm"
      @change="patch({ field: ($event.target as HTMLSelectElement).value })"
    >
      <option value="" disabled>campo</option>
      <option v-for="f in fields" :key="f" :value="f">{{ f }}</option>
    </select>

    <select
      data-testid="condition-op"
      :value="modelValue.op"
      class="rounded-md border border-default bg-default px-2 py-1.5 text-sm"
      @change="patch({ op: ($event.target as HTMLSelectElement).value })"
    >
      <option v-for="o in ops" :key="o" :value="o">{{ o }}</option>
    </select>

    <input
      data-testid="condition-value"
      :value="modelValue.value"
      placeholder="valor"
      class="rounded-md border border-default bg-default px-2 py-1.5 text-sm"
      @input="patch({ value: ($event.target as HTMLInputElement).value })"
    >

    <button
      data-testid="condition-remove"
      type="button"
      class="rounded-md px-2 py-1 text-sm text-muted hover:text-error"
      @click="emit('remove')"
    >
      remover
    </button>
  </div>
</template>
