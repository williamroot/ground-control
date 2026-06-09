<script setup lang="ts">
import type { Timer } from '~/composables/useTimers'

// Display + controles do timer de um ticket (#1J fase 3). Três estados VISUAIS
// distintos — idle (neutro), running (verde, pulsando, ticando) e paused
// (âmbar, congelado). `size` alterna entre célula compacta (lista) e card
// proeminente (detalhe). Cores SEMÂNTICAS apenas — nunca a cor de marca.
const props = withDefaults(defineProps<{
  znunyTicketId: number
  timer: Timer | null
  size?: 'sm' | 'lg'
  busy?: boolean
}>(), {
  size: 'sm',
  busy: false,
})

const emit = defineEmits<{
  start: []
  pause: []
  resume: []
  stop: []
}>()

const { elapsed, formatHMS, now } = useTimers()

const state = computed<'idle' | 'running' | 'paused'>(() => {
  if (!props.timer) return 'idle'
  return props.timer.status === 'running' ? 'running' : 'paused'
})

// Recomputa a cada segundo via `now` enquanto rodando (elapsed lê `now`).
const display = computed(() => {
  void now.value
  return props.timer ? formatHMS(elapsed(props.timer)) : '00:00:00'
})

const isLarge = computed(() => props.size === 'lg')
</script>

<template>
  <!-- IDLE -->
  <div v-if="state === 'idle'" :class="isLarge ? 'flex flex-col items-center gap-4' : 'flex items-center justify-end gap-2'">
    <span
      v-if="isLarge"
      class="font-mono font-semibold tabular-nums tracking-tight text-dimmed text-5xl"
    >00:00:00</span>
    <UButton
      :size="isLarge ? 'xl' : 'sm'"
      color="success"
      variant="solid"
      icon="i-lucide-play"
      :loading="busy"
      :block="isLarge"
      @click="emit('start')"
    >
      Iniciar
    </UButton>
  </div>

  <!-- RUNNING -->
  <div
    v-else-if="state === 'running'"
    :class="isLarge ? 'flex flex-col items-center gap-4' : 'flex items-center justify-end gap-2'"
  >
    <div :class="isLarge ? 'flex flex-col items-center gap-1' : 'flex items-center gap-2'">
      <span class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-success">
        <span class="relative flex h-2 w-2">
          <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
          <span class="relative inline-flex h-2 w-2 rounded-full bg-success" />
        </span>
        em curso
      </span>
      <span
        class="font-mono font-semibold tabular-nums tracking-tight text-success"
        :class="isLarge ? 'text-6xl' : 'text-base'"
      >{{ display }}</span>
    </div>
    <div class="flex items-center gap-2">
      <UButton
        :size="isLarge ? 'xl' : 'sm'"
        color="warning"
        variant="soft"
        icon="i-lucide-pause"
        :loading="busy"
        :square="!isLarge"
        @click="emit('pause')"
      >
        <span v-if="isLarge">Pausar</span>
      </UButton>
      <UButton
        :size="isLarge ? 'xl' : 'sm'"
        color="error"
        variant="soft"
        icon="i-lucide-square"
        :square="!isLarge"
        @click="emit('stop')"
      >
        <span v-if="isLarge">Encerrar</span>
      </UButton>
    </div>
  </div>

  <!-- PAUSED -->
  <div
    v-else
    :class="isLarge ? 'flex flex-col items-center gap-4' : 'flex items-center justify-end gap-2'"
  >
    <div :class="isLarge ? 'flex flex-col items-center gap-1' : 'flex items-center gap-2'">
      <span class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-warning">
        <UIcon name="i-lucide-pause" class="h-3.5 w-3.5" />
        pausado
      </span>
      <span
        class="font-mono font-semibold tabular-nums tracking-tight text-warning"
        :class="isLarge ? 'text-6xl' : 'text-base'"
      >{{ display }}</span>
    </div>
    <div class="flex items-center gap-2">
      <UButton
        :size="isLarge ? 'xl' : 'sm'"
        color="success"
        variant="soft"
        icon="i-lucide-play"
        :loading="busy"
        :square="!isLarge"
        @click="emit('resume')"
      >
        <span v-if="isLarge">Retomar</span>
      </UButton>
      <UButton
        :size="isLarge ? 'xl' : 'sm'"
        color="error"
        variant="soft"
        icon="i-lucide-square"
        :square="!isLarge"
        @click="emit('stop')"
      >
        <span v-if="isLarge">Encerrar</span>
      </UButton>
    </div>
  </div>
</template>
