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
  { to: '/analytics', label: 'Analytics' },
  // Onda 3 (R18b) — o entregável que a Gerti manda para os clientes todo mês.
  { to: '/relatorios', label: 'Relatórios' },
  // Onda 4 (R8) — a migração do TIFLUX são 60 clientes; não dá para um a um.
  { to: '/importacoes', label: 'Importações' },
  { to: '/automacoes', label: 'Automações' },
  // Spec #3 — telas de outros agentes (V5/V6); linkadas aqui mesmo antes de
  // existirem, conforme o contrato da spec.
  { to: '/auditoria', label: 'Auditoria' },
  { to: '/sistema', label: 'Sistema' },
  { to: '/busca', label: 'Busca' },
]

// Spec #4 — capa de administração do Znuny (7 rotas). Só duas (filas, sla)
// existem nesta etapa; as outras cinco são de outros agentes em paralelo e
// entram no menu mesmo antes de existirem, conforme o contrato da spec.
const znunyLinks = [
  { to: '/znuny/filas', label: 'Filas (mesas de serviço)' },
  { to: '/znuny/sla', label: 'SLA' },
  { to: '/znuny/servicos', label: 'Serviços' },
  { to: '/znuny/classificacao', label: 'Classificação' },
  { to: '/znuny/classes-ci', label: 'Classes de CI' },
  { to: '/znuny/agentes', label: 'Agentes' },
  { to: '/znuny/calendario', label: 'Calendário' },
  // Onda 2 (R9) — entrada, saída e domínios autorizados numa tela só.
  { to: '/znuny/email', label: 'E-mail' },
]
const znunyMenuOpen = ref(false)
const isZnunyRoute = computed(() => route.path.startsWith('/znuny/'))
watch(() => route.path, () => { znunyMenuOpen.value = false })
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
          <img src="/favicon.svg" alt="Ground Control" class="h-8 w-8 rounded-lg shadow-sm">
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

          <!-- Spec #4 — grupo Znuny (filas, SLA, serviços, classificação, -->
          <!-- classes de CI, agentes, calendário) numa única entrada. -->
          <div class="relative">
            <button
              type="button"
              data-testid="nav-znuny-toggle"
              class="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm font-medium text-muted transition hover:bg-elevated hover:text-default"
              :class="{ 'bg-elevated text-highlighted': isZnunyRoute }"
              @click="znunyMenuOpen = !znunyMenuOpen"
            >
              Znuny
              <UIcon name="i-lucide-chevron-down" class="h-3.5 w-3.5" />
            </button>
            <div
              v-if="znunyMenuOpen"
              data-testid="nav-znuny-menu"
              class="absolute left-0 top-full z-20 mt-1 w-56 rounded-lg border border-default bg-default p-1 shadow-lg"
            >
              <ULink
                v-for="link in znunyLinks"
                :key="link.to"
                :to="link.to"
                class="block rounded-md px-3 py-1.5 text-sm text-muted transition hover:bg-elevated hover:text-default"
                active-class="bg-elevated text-highlighted"
              >
                {{ link.label }}
              </ULink>
            </div>
          </div>
        </nav>
      </div>
    </header>

    <main class="flex-1">
      <slot />
    </main>
  </div>
</template>
