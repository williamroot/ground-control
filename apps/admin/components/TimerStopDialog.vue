<script setup lang="ts">
import type { Timer } from '~/composables/useTimers'

// Diálogo de encerramento do timer (#1J fase 3). Dead-simple: mostra o tempo
// decorrido, pré-preenche os MINUTOS arredondados (editáveis) e uma NOTA, e
// lança com um único botão "Lançar". Reutilizado pela lista e pelo detalhe.
const props = defineProps<{
  timer: Timer | null
  ticketLabel?: string
}>()

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  launched: []
}>()

const { elapsed, formatHMS, stop } = useTimers()
const toast = useToast()

const minutes = ref<number>(0)
const note = ref<string>('')
const submitting = ref(false)
const errorMsg = ref('')

const elapsedSeconds = computed(() =>
  props.timer ? elapsed(props.timer) : 0)
const elapsedDisplay = computed(() => formatHMS(elapsedSeconds.value))

// Ao abrir, congela o tempo e pré-preenche minutos arredondados (mín. 1).
watch(open, (isOpen) => {
  if (isOpen && props.timer) {
    minutes.value = Math.max(1, Math.round(elapsedSeconds.value / 60))
    note.value = ''
    errorMsg.value = ''
  }
})

async function launch() {
  if (!props.timer) return
  errorMsg.value = ''
  const m = Number(minutes.value)
  if (Number.isNaN(m) || m < 0) {
    errorMsg.value = 'Informe um número de minutos válido.'
    return
  }
  submitting.value = true
  try {
    await stop({
      timer_id: props.timer.id,
      adjust_minutes: m,
      note: note.value.trim(),
    })
    toast.add({
      title: 'Tempo lançado',
      description: `${m} min registrados no chamado.`,
      color: 'success',
      icon: 'i-lucide-check',
    })
    open.value = false
    emit('launched')
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    errorMsg.value = err.data?.detail || 'Falha ao lançar o tempo. Tente novamente.'
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <UModal
    v-model:open="open"
    title="Lançar tempo"
    :description="ticketLabel || 'Confirme os minutos e adicione uma nota.'"
    :ui="{ footer: 'justify-end' }"
  >
    <template #body>
      <div class="space-y-5">
        <div class="flex items-center justify-between rounded-lg border border-default bg-elevated/50 px-4 py-3">
          <span class="text-sm text-muted">Tempo cronometrado</span>
          <span class="font-mono text-2xl font-semibold tabular-nums tracking-tight text-highlighted">
            {{ elapsedDisplay }}
          </span>
        </div>

        <UAlert
          v-if="errorMsg"
          color="error"
          variant="soft"
          icon="i-lucide-alert-triangle"
          :title="errorMsg"
        />

        <UFormField label="Minutos a lançar" required help="Ajuste se cronometrou tempo a mais ou a menos.">
          <UInput v-model.number="minutes" type="number" min="0" step="1" size="lg" class="w-full">
            <template #trailing>
              <span class="text-xs text-muted">min</span>
            </template>
          </UInput>
        </UFormField>

        <UFormField label="Nota" help="Resumo do que foi feito (opcional).">
          <UTextarea v-model="note" :rows="3" placeholder="Ex.: Ajuste na configuração de e-mail do cliente." class="w-full" />
        </UFormField>
      </div>
    </template>

    <template #footer="{ close }">
      <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="submitting" @click="close" />
      <UButton
        label="Lançar"
        color="primary"
        icon="i-lucide-check"
        :loading="submitting"
        @click="launch"
      />
    </template>
  </UModal>
</template>
