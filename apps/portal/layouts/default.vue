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
  // White-label: favicon = logo do tenant quando há; senão o default neutro
  // (NUNCA a marca Gerti/Ground Control aqui).
  link: [{
    rel: 'icon',
    href: b.value?.logo_url || '/favicon.svg',
    type: b.value?.logo_url ? undefined : 'image/svg+xml',
  }],
}))

// A top bar/logout só aparece nas páginas autenticadas (não no /login).
const route = useRoute()
const isAuthedView = computed(() => route.path !== '/login')

// Nav por papel (Spec #1H): admin vê Contratos; help-desk vê Tickets.
// Sem await: a nav é progressiva e lê o `me` já resolvido pela middleware `auth`
// (mesma key 'me' do useAsyncData) — não bloqueia o render do layout.
const { data: me } = useMe()
const role = computed(() => me.value?.role)
const isActive = (path: string) =>
  path === '/' ? route.path === '/' : route.path.startsWith(path)

async function logout() {
  await $fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
  await navigateTo('/login')
}
</script>

<template>
  <div class="min-h-screen flex flex-col bg-muted text-default">
    <!-- faixa de acento da marca -->
    <div class="h-[3px] w-full" :style="{ background: 'var(--brand-primary)' }" />

    <header
      v-if="isAuthedView"
      class="sticky top-0 z-10 border-b border-default bg-default/85 backdrop-blur"
    >
      <div class="mx-auto flex max-w-6xl items-center gap-3 px-5 py-3">
        <span
          class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-sm font-bold text-white shadow-sm font-display"
          :style="{ background: 'linear-gradient(135deg, var(--brand-primary), var(--brand-accent))' }"
        >{{ (b?.display_name ?? 'P').charAt(0) }}</span>
        <span class="font-display text-lg font-bold tracking-tight">
          {{ b?.display_name ?? 'Portal' }}
        </span>

        <!-- Nav por papel (#1H/#1E): admin -> Contratos + Chamados;
             help-desk -> Chamados. -->
        <nav v-if="role" class="ml-5 hidden items-center gap-1 sm:flex">
          <NuxtLink
            v-if="role === 'admin'"
            to="/"
            class="rounded-lg px-3 py-1.5 text-sm font-medium transition"
            :class="isActive('/') ? 'text-highlighted' : 'text-muted hover:text-highlighted'"
            :style="isActive('/') ? { background: 'color-mix(in srgb, var(--brand-primary) 12%, transparent)' } : {}"
          >Contratos</NuxtLink>
          <NuxtLink
            v-if="role === 'admin' || role === 'helpdesk'"
            to="/tickets"
            class="rounded-lg px-3 py-1.5 text-sm font-medium transition"
            :class="isActive('/tickets') ? 'text-highlighted' : 'text-muted hover:text-highlighted'"
            :style="isActive('/tickets') ? { background: 'color-mix(in srgb, var(--brand-primary) 12%, transparent)' } : {}"
          >Chamados</NuxtLink>
          <NuxtLink
            v-if="role === 'admin' || role === 'helpdesk'"
            to="/ativos"
            class="rounded-lg px-3 py-1.5 text-sm font-medium transition"
            :class="isActive('/ativos') ? 'text-highlighted' : 'text-muted hover:text-highlighted'"
            :style="isActive('/ativos') ? { background: 'color-mix(in srgb, var(--brand-primary) 12%, transparent)' } : {}"
          >Ativos</NuxtLink>
          <NuxtLink
            v-if="role === 'admin'"
            to="/faturas"
            class="rounded-lg px-3 py-1.5 text-sm font-medium transition"
            :class="isActive('/faturas') ? 'text-highlighted' : 'text-muted hover:text-highlighted'"
            :style="isActive('/faturas') ? { background: 'color-mix(in srgb, var(--brand-primary) 12%, transparent)' } : {}"
          >Faturas</NuxtLink>
        </nav>

        <div class="ml-auto flex items-center gap-3">
          <a
            v-if="b?.support_email"
            :href="`mailto:${b.support_email}`"
            class="hidden text-sm text-muted transition hover:text-highlighted sm:inline"
          >{{ b.support_email }}</a>
          <ThemeToggle />
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
      class="border-t border-default px-5 py-4 text-center"
    >
      <p v-if="b?.support_email" class="mb-1 text-xs text-dimmed">
        {{ b.display_name }} · {{ b.support_email }}
      </p>
      <WasSignature />
    </footer>
  </div>
</template>
