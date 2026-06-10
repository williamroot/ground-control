<script setup lang="ts">
// #1R-a — bloco "comando de instalação" mostrado UMA vez após gerar o token.
// HTML nativo (sem U*/@nuxt/icon) p/ montar limpo no vitest (lição #1M..#1Q).
// O token aparece em claro só aqui; o servidor guarda apenas o sha256.
import { computed, ref } from 'vue'
import { buildInstallCommand } from '../../composables/useAgents'

const props = defineProps<{
  server: string
  token: string
}>()

const command = computed(() => buildInstallCommand(props.server, props.token))
const copied = ref(false)

async function copy() {
  try {
    await navigator.clipboard.writeText(command.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  }
  catch {
    copied.value = false
  }
}
</script>

<template>
  <div data-testid="install-command" class="rounded-xl border border-warning/40 bg-warning/5 p-4">
    <p class="mb-2 text-xs font-semibold uppercase tracking-wide text-warning">
      Token de instalação — copie agora (não será mostrado de novo)
    </p>
    <div class="flex items-start gap-2">
      <code
        data-testid="install-text"
        class="flex-1 overflow-x-auto whitespace-pre rounded-md bg-default px-3 py-2 font-mono text-xs text-highlighted"
      >{{ command }}</code>
      <button
        type="button"
        data-testid="copy-install"
        class="shrink-0 rounded-md border border-default bg-elevated px-3 py-2 text-xs font-medium text-default hover:bg-default"
        @click="copy"
      >
        {{ copied ? 'Copiado!' : 'Copiar' }}
      </button>
    </div>
  </div>
</template>
