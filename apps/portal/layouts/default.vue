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

// A top bar/logout só aparece nas páginas autenticadas (não no /login).
const route = useRoute()
const isAuthedView = computed(() => route.path !== '/login')

async function logout() {
  await $fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
  await navigateTo('/login')
}
</script>

<template>
  <div class="min-h-screen flex flex-col bg-[#faf9f8] text-[#1f2733]">
    <!-- faixa de acento da marca -->
    <div class="h-[3px] w-full" :style="{ background: 'var(--brand-primary)' }" />

    <header
      v-if="isAuthedView"
      class="sticky top-0 z-10 border-b border-neutral-200/70 bg-white/85 backdrop-blur"
    >
      <div class="mx-auto flex max-w-6xl items-center gap-3 px-5 py-3">
        <span
          class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-sm font-bold text-white shadow-sm font-display"
          :style="{ background: 'linear-gradient(135deg, var(--brand-primary), var(--brand-accent))' }"
        >{{ (b?.display_name ?? 'P').charAt(0) }}</span>
        <span class="font-display text-lg font-bold tracking-tight">
          {{ b?.display_name ?? 'Portal' }}
        </span>
        <div class="ml-auto flex items-center gap-3">
          <a
            v-if="b?.support_email"
            :href="`mailto:${b.support_email}`"
            class="hidden text-sm text-neutral-500 transition hover:text-neutral-800 sm:inline"
          >{{ b.support_email }}</a>
          <UButton
            color="neutral"
            variant="ghost"
            size="sm"
            icon="i-lucide-log-out"
            @click="logout"
          >Sair</UButton>
        </div>
      </div>
    </header>

    <main class="flex-1">
      <slot />
    </main>

    <footer
      v-if="isAuthedView"
      class="border-t border-neutral-200/70 px-5 py-4 text-center"
    >
      <p v-if="b?.support_email" class="mb-1 text-xs text-neutral-400">
        {{ b.display_name }} · {{ b.support_email }}
      </p>
      <WasSignature />
    </footer>
  </div>
</template>
