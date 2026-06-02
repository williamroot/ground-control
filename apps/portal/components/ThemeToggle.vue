<script setup lang="ts">
// Seletor de tema claro/escuro/sistema. Persistido por @nuxtjs/color-mode
// (cookie/localStorage). `system` segue o SO. Segmentado (3 botões) em vez de
// dropdown: escolha explícita, sem API de menu, e cabe no header.
const colorMode = useColorMode()

const options = [
  { value: 'light', icon: 'i-lucide-sun', label: 'Claro' },
  { value: 'system', icon: 'i-lucide-monitor', label: 'Sistema' },
  { value: 'dark', icon: 'i-lucide-moon', label: 'Escuro' },
] as const
</script>

<template>
  <ClientOnly>
    <div
      class="inline-flex items-center gap-0.5 rounded-lg border border-default bg-default p-0.5"
      role="group"
      aria-label="Tema"
    >
      <button
        v-for="o in options"
        :key="o.value"
        type="button"
        :aria-label="o.label"
        :aria-pressed="colorMode.preference === o.value"
        :title="o.label"
        class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted transition hover:text-highlighted"
        :class="colorMode.preference === o.value ? 'bg-elevated text-highlighted' : ''"
        @click="colorMode.preference = o.value"
      >
        <UIcon :name="o.icon" class="h-4 w-4" />
      </button>
    </div>
    <template #fallback>
      <div class="h-8 w-[88px]" />
    </template>
  </ClientOnly>
</template>
