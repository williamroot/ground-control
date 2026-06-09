<script setup lang="ts">
// #1M — widget de avaliação CSAT 1-5 inline no detalhe do ticket.
// H8: notas/estados usam cores SEMÂNTICAS do Nuxt UI (neutral/warning/success/
// error via tokens text-*), NUNCA a cor de marca (--brand-primary/-accent).
// A marca é só identidade.
//
// Componente puro (HTML nativo + SVG inline, SSR-safe — mesmo padrão dos
// charts/WasSignature) para não depender do boot do Nuxt UI nos unit tests.
// Emite `submit` com { score, comment }. Com `submittedScore` definido,
// renderiza o estado "respondido" (mostra a nota, esconde o form).

const props = defineProps<{
  submittedScore?: number | null
  loading?: boolean
}>()

const emit = defineEmits<{ submit: [{ score: number, comment: string }] }>()

const score = ref<number | null>(null)
const comment = ref('')

const submitted = computed(() => typeof props.submittedScore === 'number')

// Escala semântica: 1-2 baixo (error), 3 médio (warning), 4-5 alto (success).
// Tokens textuais do Nuxt UI que adaptam a tema claro/escuro.
function scoreColor(n: number): string {
  if (n <= 2) return 'text-error'
  if (n === 3) return 'text-warning'
  return 'text-success'
}

const SCORE_LABELS: Record<number, string> = {
  1: 'Muito insatisfeito',
  2: 'Insatisfeito',
  3: 'Neutro',
  4: 'Satisfeito',
  5: 'Muito satisfeito',
}

function pick(n: number) {
  score.value = n
}

function onSubmit() {
  if (score.value == null) return
  emit('submit', { score: score.value, comment: comment.value.trim() })
}
</script>

<template>
  <div class="rounded-xl border border-default bg-elevated px-4 py-4">
    <!-- Estado: já respondido -->
    <div v-if="submitted" class="flex items-center gap-3" data-csat-answered>
      <span
        class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-success/15 text-success"
        aria-hidden="true"
      >
        <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </span>
      <div>
        <p class="text-sm font-semibold text-highlighted">Obrigado pela sua avaliação!</p>
        <p class="text-sm text-muted">
          Sua nota:
          <span class="font-semibold" :class="scoreColor(submittedScore as number)">{{ submittedScore }}/5</span>
        </p>
      </div>
    </div>

    <!-- Estado: pendente (form) -->
    <div v-else>
      <p class="text-sm font-semibold text-highlighted">Como foi o seu atendimento?</p>
      <p class="mt-0.5 text-xs text-muted">Avalie de 1 (ruim) a 5 (ótimo).</p>

      <div class="mt-3 flex items-center gap-2" role="radiogroup" aria-label="Nota de 1 a 5">
        <button
          v-for="n in 5"
          :key="n"
          type="button"
          data-csat-score
          :data-score="n"
          :aria-label="SCORE_LABELS[n]"
          :aria-pressed="score === n"
          class="inline-flex h-10 w-10 items-center justify-center rounded-lg border transition"
          :class="score != null && n <= score
            ? [scoreColor(score), 'border-current bg-default']
            : 'border-default text-dimmed hover:text-muted'"
          @click="pick(n)"
        >
          <svg
            viewBox="0 0 24 24"
            class="h-5 w-5"
            :fill="score != null && n <= score ? 'currentColor' : 'none'"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M11.48 3.5a.56.56 0 011.04 0l2.12 4.3 4.75.69a.56.56 0 01.31.96l-3.44 3.35.81 4.73a.56.56 0 01-.81.59L12 16.9l-4.25 2.23a.56.56 0 01-.81-.59l.81-4.73L4.3 9.45a.56.56 0 01.31-.96l4.75-.69 2.12-4.3z"
            />
          </svg>
        </button>
        <span v-if="score != null" class="ml-2 text-xs font-medium" :class="scoreColor(score)">
          {{ SCORE_LABELS[score] }}
        </span>
      </div>

      <textarea
        v-model="comment"
        :rows="3"
        placeholder="Quer deixar um comentário? (opcional)"
        aria-label="Comentário opcional"
        class="mt-3 w-full rounded-lg border border-default bg-default px-3 py-2 text-sm text-default placeholder:text-dimmed focus:border-current focus:outline-none"
      />

      <div class="mt-3 flex justify-end">
        <button
          type="button"
          data-csat-submit
          class="inline-flex items-center gap-1.5 rounded-lg border border-default bg-default px-3.5 py-2 text-sm font-medium text-highlighted transition hover:bg-elevated disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="score == null || loading"
          @click="onSubmit"
        >
          <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14M13 6l6 6-6 6" />
          </svg>
          {{ loading ? 'Enviando…' : 'Enviar avaliação' }}
        </button>
      </div>
    </div>
  </div>
</template>
