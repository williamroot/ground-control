<script setup lang="ts">
// Grade clicável 7 dias x 24 horas (Spec #4, Bloco D). HTML nativo de
// propósito — monta limpo no vitest sem contexto Nuxt (lição #1M..#1P).
// Seleção por clique (toggle), por arrasto (mousedown + mouseenter em
// sequência) e por faixa (shift-clique no mesmo dia). Tokens semânticos
// apenas: `bg-primary` marca hora útil (mesma cor de marca usada na
// navegação do console), `bg-elevated`/`border-default` marcam hora livre —
// fica legível em claro e escuro porque são tokens, não hex cru.
import type { DayKey, WorkingGrid } from '../../composables/useWorkingHours'
import {
  applyShortcut,
  DAY_KEYS,
  DAY_LABELS,
  DAY_LABELS_SHORT,
  HOURS,
  SHORTCUTS,
  setCell,
  toggleHourRange,
  weeklyTotalHours,
} from '../../composables/useWorkingHours'

const props = defineProps<{ modelValue: WorkingGrid }>()
const emit = defineEmits<{ 'update:modelValue': [WorkingGrid] }>()

const painting = ref(false)
const paintValue = ref(true)
const rangeAnchor = ref<{ day: DayKey, hour: number } | null>(null)

function isOn(day: DayKey, hour: number): boolean {
  return props.modelValue[day]?.[hour] ?? false
}

function onCellMouseDown(day: DayKey, hour: number, shiftKey: boolean) {
  if (shiftKey && rangeAnchor.value && rangeAnchor.value.day === day) {
    const value = !isOn(day, rangeAnchor.value.hour)
    emit('update:modelValue', toggleHourRange(props.modelValue, day, rangeAnchor.value.hour, hour, value))
    return
  }
  painting.value = true
  paintValue.value = !isOn(day, hour)
  rangeAnchor.value = { day, hour }
  emit('update:modelValue', setCell(props.modelValue, day, hour, paintValue.value))
}

function onCellEnter(day: DayKey, hour: number) {
  if (!painting.value) return
  emit('update:modelValue', setCell(props.modelValue, day, hour, paintValue.value))
}

function stopPaint() {
  painting.value = false
}

// SSR-safe: só toca em `window` depois de montado no cliente.
onMounted(() => {
  window.addEventListener('mouseup', stopPaint)
})
onBeforeUnmount(() => {
  window.removeEventListener('mouseup', stopPaint)
})

function runShortcut(key: 'business' | 'all' | 'clear') {
  emit('update:modelValue', applyShortcut(key))
}

const total = computed(() => weeklyTotalHours(props.modelValue))
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap gap-2">
      <button
        v-for="s in SHORTCUTS"
        :key="s.key"
        type="button"
        :data-testid="`shortcut-${s.key}`"
        class="rounded-md border border-default bg-default px-3 py-1.5 text-xs font-medium text-default hover:bg-elevated"
        @click="runShortcut(s.key)"
      >
        {{ s.label }}
      </button>
    </div>

    <div class="overflow-x-auto rounded-lg border border-default p-2">
      <table class="w-full select-none border-collapse text-[11px]">
        <thead>
          <tr>
            <th class="w-12 p-1 text-left font-normal text-dimmed" />
            <th v-for="h in HOURS" :key="h" class="p-0.5 text-center font-normal text-dimmed">
              {{ h }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="day in DAY_KEYS" :key="day">
            <th
              class="whitespace-nowrap p-1 text-left text-xs font-medium text-default"
              :title="DAY_LABELS[day]"
            >
              {{ DAY_LABELS_SHORT[day] }}
            </th>
            <td v-for="h in HOURS" :key="h" class="p-0.5">
              <button
                type="button"
                :data-testid="`hour-cell-${day}-${h}`"
                :aria-pressed="isOn(day, h)"
                :aria-label="`${DAY_LABELS[day]} às ${h}h`"
                class="block h-5 w-5 rounded-sm border transition-colors"
                :class="isOn(day, h)
                  ? 'border-primary bg-primary'
                  : 'border-default bg-elevated hover:bg-accented'"
                @mousedown.prevent="onCellMouseDown(day, h, $event.shiftKey)"
                @mouseenter="onCellEnter(day, h)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="mt-3 text-sm text-muted">
      Total de horas úteis por semana:
      <span data-testid="weekly-total" class="font-semibold text-highlighted">{{ total }}</span>
    </p>
  </div>
</template>
