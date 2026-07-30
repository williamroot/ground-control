<script setup lang="ts">
// Feriados recorrentes (TimeVacationDays: mês -> dia -> texto, repetem todo
// ano). HTML nativo de propósito (monta limpo no vitest sem contexto Nuxt).
// Ordenado por data e agrupado por mês, como pedido na spec.
import type { RecurringHoliday } from '../../composables/useWorkingHours'
import { emptyRecurringHoliday, MONTH_LABELS, validateRecurringHoliday } from '../../composables/useWorkingHours'

const props = defineProps<{ modelValue: RecurringHoliday[] }>()
const emit = defineEmits<{ 'update:modelValue': [RecurringHoliday[]] }>()

const draft = ref<RecurringHoliday>(emptyRecurringHoliday())
const editingIndex = ref<number | null>(null)
const errors = ref<string[]>([])

interface Grouped { key: string, label: string, items: (RecurringHoliday & { index: number })[] }

const groups = computed<Grouped[]>(() => {
  const decorated = props.modelValue.map((h, index) => ({ ...h, index }))
  decorated.sort((a, b) => a.month - b.month || a.day - b.day)
  const out: Grouped[] = []
  for (const item of decorated) {
    const key = String(item.month)
    let group = out.find(g => g.key === key)
    if (!group) {
      group = { key, label: MONTH_LABELS[item.month - 1] ?? `Mês ${item.month}`, items: [] }
      out.push(group)
    }
    group.items.push(item)
  }
  return out
})

function startEdit(index: number) {
  const item = props.modelValue[index]
  if (!item) return
  draft.value = { ...item }
  editingIndex.value = index
  errors.value = []
}

function cancelEdit() {
  draft.value = emptyRecurringHoliday()
  editingIndex.value = null
  errors.value = []
}

function remove(index: number) {
  emit('update:modelValue', props.modelValue.filter((_, i) => i !== index))
  if (editingIndex.value === index) cancelEdit()
}

function submit() {
  const v = validateRecurringHoliday(draft.value)
  if (v.length > 0) {
    errors.value = v
    return
  }
  const clean: RecurringHoliday = {
    month: Number(draft.value.month),
    day: Number(draft.value.day),
    description: draft.value.description.trim(),
  }
  if (editingIndex.value === null) {
    emit('update:modelValue', [...props.modelValue, clean])
  }
  else {
    const next = [...props.modelValue]
    next[editingIndex.value] = clean
    emit('update:modelValue', next)
  }
  cancelEdit()
}
</script>

<template>
  <div class="space-y-4">
    <div class="space-y-2 rounded-lg border border-default p-3">
      <div class="grid grid-cols-3 gap-2">
        <select
          v-model.number="draft.month"
          data-testid="recurring-month"
          aria-label="Mês"
          class="rounded-md border border-default bg-default px-2 py-1.5 text-sm text-default"
        >
          <option v-for="(label, i) in MONTH_LABELS" :key="i" :value="i + 1">{{ label }}</option>
        </select>
        <input
          v-model.number="draft.day"
          data-testid="recurring-day"
          type="number"
          min="1"
          max="31"
          placeholder="Dia"
          aria-label="Dia"
          class="rounded-md border border-default bg-default px-2 py-1.5 text-sm text-default"
        >
        <input
          v-model="draft.description"
          data-testid="recurring-description"
          type="text"
          placeholder="Descrição"
          aria-label="Descrição do feriado"
          class="rounded-md border border-default bg-default px-2 py-1.5 text-sm text-default"
        >
      </div>

      <p v-if="errors.length > 0" data-testid="recurring-error" class="text-xs text-error">
        {{ errors.join(' ') }}
      </p>

      <div class="flex gap-2">
        <button
          type="button"
          data-testid="recurring-submit"
          class="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-inverted"
          @click="submit"
        >
          {{ editingIndex === null ? 'Adicionar' : 'Salvar' }}
        </button>
        <button
          v-if="editingIndex !== null"
          type="button"
          data-testid="recurring-cancel"
          class="rounded-md border border-default px-3 py-1.5 text-xs font-medium text-default"
          @click="cancelEdit"
        >
          Cancelar edição
        </button>
      </div>
    </div>

    <p v-if="modelValue.length === 0" class="text-sm text-muted">
      Nenhum feriado recorrente cadastrado.
    </p>

    <div v-else class="space-y-3">
      <div v-for="group in groups" :key="group.key">
        <p class="mb-1 text-xs font-medium uppercase tracking-wide text-dimmed">{{ group.label }}</p>
        <ul class="divide-y divide-default rounded-lg border border-default">
          <li
            v-for="item in group.items"
            :key="item.index"
            class="flex items-center justify-between gap-2 px-3 py-2 text-sm"
          >
            <span class="text-default">
              <span class="font-medium">{{ String(item.day).padStart(2, '0') }}/{{ String(item.month).padStart(2, '0') }}</span>
              — {{ item.description }}
            </span>
            <span class="flex shrink-0 gap-2">
              <button
                type="button"
                data-testid="recurring-edit"
                class="text-xs text-muted hover:text-default"
                @click="startEdit(item.index)"
              >
                editar
              </button>
              <button
                type="button"
                data-testid="recurring-remove"
                class="text-xs text-error hover:underline"
                @click="remove(item.index)"
              >
                remover
              </button>
            </span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
