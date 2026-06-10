<script setup lang="ts">
// Linha de ação do editor de regras (#1Q). HTML nativo. Emite {type, params}.
// O input do parâmetro principal é dirigido por ACTION_PARAM_KEY (a chave
// esperada por cada tipo de ação); ai_summarize_note não tem parâmetro.
import { computed } from 'vue'
import { ACTION_PARAM_KEY, type RuleAction } from '../../composables/useAutomationRule'

const props = defineProps<{
  modelValue: RuleAction
  actions: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: RuleAction]
  'remove': []
}>()

const paramKey = computed(() => ACTION_PARAM_KEY[props.modelValue.type] ?? '')

function setType(type: string) {
  // ao trocar o tipo, reseta os params (chave muda).
  emit('update:modelValue', { type, params: {} })
}

function setParam(value: string) {
  const key = paramKey.value
  if (!key) return
  emit('update:modelValue', { ...props.modelValue, params: { [key]: value } })
}
</script>

<template>
  <div data-testid="action-row" class="flex flex-wrap items-center gap-2">
    <select
      data-testid="action-type"
      :value="modelValue.type"
      class="rounded-md border border-default bg-default px-2 py-1.5 text-sm"
      @change="setType(($event.target as HTMLSelectElement).value)"
    >
      <option value="" disabled>ação</option>
      <option v-for="a in actions" :key="a" :value="a">{{ a }}</option>
    </select>

    <input
      v-if="paramKey"
      data-testid="action-param"
      :value="modelValue.params[paramKey] ?? ''"
      :placeholder="paramKey"
      class="rounded-md border border-default bg-default px-2 py-1.5 text-sm"
      @input="setParam(($event.target as HTMLInputElement).value)"
    >
    <span v-else data-testid="action-noparam" class="text-sm text-muted">sem parâmetro</span>

    <button
      data-testid="action-remove"
      type="button"
      class="rounded-md px-2 py-1 text-sm text-muted hover:text-error"
      @click="emit('remove')"
    >
      remover
    </button>
  </div>
</template>
