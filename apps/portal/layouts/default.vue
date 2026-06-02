<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

// #1F-a: ler o branding do event.context que o server/middleware/branding.ts
// JÁ populou na requisição ORIGINAL (com o Host/x-forwarded-host do tenant).
// NÃO usar $fetch('/api/branding-context'): em SSR aquilo é uma sub-request
// interna que NÃO carrega o Host do tenant → o middleware reexecuta sem host
// → resolveSubdomain null → DEFAULT_BRANDING para todo tenant.
// useState serializa o valor do SSR para o cliente (sem flash/mismatch).
const event = useRequestEvent()
const branding = useState<Branding>('branding', () =>
  (event?.context?.branding as Branding | undefined) ?? DEFAULT_BRANDING)

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
