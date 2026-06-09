<script setup lang="ts">
// Painel de IA no detalhe do atendimento (#1N): "Resumir com IA" + "Sugerir
// resposta". HTML/SVG NATIVO (sem U*/@nuxt/icon) para montar limpo no vitest
// (lição do #1M). O texto do LLM é renderizado ESCAPADO (interpolação Vue padrão,
// nunca v-html — camada 5 da defesa contra prompt injection). O resultado de
// resposta é um RASCUNHO: o botão "usar como rascunho" emite use-draft p/ o
// textarea de resposta; o agente edita e envia manualmente (nunca auto-send).
withDefaults(defineProps<{
  ticketId: number
  aiEnabled: boolean
  loading?: boolean
  error?: string | null
  result?: { kind: 'summary' | 'reply', text: string } | null
}>(), {
  loading: false,
  error: null,
  result: null,
})

const emit = defineEmits<{
  summarize: []
  suggest: []
  'use-draft': [text: string]
}>()
</script>

<template>
  <section
    v-if="aiEnabled"
    data-testid="ai-panel"
    class="rounded-2xl border border-default bg-default p-5"
  >
    <header class="mb-3 flex items-center gap-2">
      <!-- ícone sparkles SVG inline (sem @nuxt/icon) -->
      <svg
        class="h-4 w-4 text-primary"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
      </svg>
      <h2 class="font-display text-sm font-bold text-highlighted">
        Assistente de IA
      </h2>
    </header>

    <div class="flex flex-wrap gap-2">
      <button
        type="button"
        data-testid="ai-summarize"
        class="inline-flex items-center gap-1.5 rounded-lg border border-default bg-elevated px-3 py-1.5 text-sm font-medium text-default transition hover:bg-accented disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="loading"
        @click="emit('summarize')"
      >
        Resumir com IA
      </button>
      <button
        type="button"
        data-testid="ai-suggest"
        class="inline-flex items-center gap-1.5 rounded-lg border border-default bg-elevated px-3 py-1.5 text-sm font-medium text-default transition hover:bg-accented disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="loading"
        @click="emit('suggest')"
      >
        Sugerir resposta
      </button>
    </div>

    <!-- loading skeleton (SVG/HTML nativo) -->
    <div v-if="loading" data-testid="ai-loading" class="mt-4 space-y-2">
      <div class="h-3 w-3/4 animate-pulse rounded bg-elevated" />
      <div class="h-3 w-full animate-pulse rounded bg-elevated" />
      <div class="h-3 w-1/2 animate-pulse rounded bg-elevated" />
    </div>

    <!-- erro -->
    <p
      v-else-if="error"
      data-testid="ai-error"
      class="mt-4 rounded-lg border border-error/30 bg-error/5 px-3 py-2 text-sm text-error"
    >
      {{ error }}
    </p>

    <!-- resultado — texto ESCAPADO (interpolação, nunca v-html) -->
    <div v-else-if="result" class="mt-4">
      <p class="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">
        {{ result.kind === 'summary' ? 'Resumo' : 'Rascunho de resposta' }}
      </p>
      <div
        data-testid="ai-result"
        class="whitespace-pre-wrap break-words rounded-lg border border-default bg-muted/40 px-3 py-2.5 text-sm text-toned"
      >{{ result.text }}</div>
      <p v-if="result.kind === 'reply'" class="mt-1.5 text-xs text-dimmed">
        Rascunho gerado por IA — revise antes de enviar ao cliente.
      </p>
      <button
        v-if="result.kind === 'reply'"
        type="button"
        data-testid="ai-use-draft"
        class="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/10 px-3 py-1.5 text-sm font-medium text-primary transition hover:bg-primary/15"
        @click="emit('use-draft', result.text)"
      >
        Usar como rascunho
      </button>
    </div>
  </section>
</template>
