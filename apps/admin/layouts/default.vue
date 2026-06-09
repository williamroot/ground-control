<script setup lang="ts">
import { ADMIN_IDENTITY } from '#shared/identity'

// Identidade FIXA Gerti (não white-label). T1.E/T1.F enriquecem (nav, sessão,
// logout real). Scaffold da Fase 0: shell mínimo com a marca Gerti.
useHead({
  title: ADMIN_IDENTITY.display_name,
})

const route = useRoute()
const isAuthedView = computed(() => route.path !== '/login')

const navLinks = [
  { to: '/', label: 'Clientes' },
  { to: '/atendimento', label: 'Atendimento' },
]
</script>

<template>
  <div class="min-h-screen flex flex-col bg-muted text-default">
    <div class="h-[3px] w-full bg-primary" />

    <header
      v-if="isAuthedView"
      class="sticky top-0 z-10 border-b border-default bg-default/85 backdrop-blur"
    >
      <div class="mx-auto flex max-w-6xl items-center gap-3 px-5 py-3">
        <NuxtLink to="/" class="flex items-center gap-3">
          <span
            class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white shadow-sm font-display"
          >G</span>
          <span class="font-display text-lg font-bold tracking-tight">
            {{ ADMIN_IDENTITY.display_name }}
          </span>
        </NuxtLink>

        <nav class="ml-4 flex items-center gap-1">
          <ULink
            v-for="link in navLinks"
            :key="link.to"
            :to="link.to"
            class="rounded-md px-3 py-1.5 text-sm font-medium text-muted transition hover:bg-elevated hover:text-default"
            active-class="bg-elevated text-highlighted"
          >
            {{ link.label }}
          </ULink>
        </nav>
      </div>
    </header>

    <main class="flex-1">
      <slot />
    </main>
  </div>
</template>
