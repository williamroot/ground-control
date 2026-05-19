<script setup lang="ts">
import type { Branding } from '~/server/middleware/branding'

const { data: branding } = await useAsyncData('branding', () =>
  $fetch<Branding>('/api/branding-context'))

const b = computed(() => branding.value)
useHead(() => ({
  style: [{
    children: `:root{--brand-primary:${b.value?.primary_color ?? '#475569'};`
      + `--brand-accent:${b.value?.accent_color ?? '#334155'};}`,
  }],
  title: b.value?.display_name ?? 'Portal',
}))
</script>

<template>
  <div class="min-h-screen" :style="{ background: 'var(--brand-primary)' }">
    <header class="p-4 text-white font-semibold">
      {{ b?.display_name ?? 'Portal' }}
    </header>
    <main class="bg-white min-h-[80vh] rounded-t-xl p-6">
      <slot />
    </main>
    <footer v-if="b?.support_email" class="p-4 text-white text-sm">
      {{ b.support_email }}
    </footer>
  </div>
</template>
