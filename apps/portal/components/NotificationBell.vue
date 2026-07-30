<script setup lang="ts">
// #3 V3 — indicador de não lidas no cabeçalho. Leva a /notificacoes.
//
// AINDA NÃO plugado em layouts/default.vue — esse arquivo é de outro agente
// da Spec #3 (dono do menu/cabeçalho). Componente pronto, com auto-import
// (`components: [{ path: '~/components', pathPrefix: false }]` no
// nuxt.config.ts) — basta inserir `<NotificationBell />` no header autenticado.
interface NotificationsResponse { unread: number }

const headers = useSidecarHeaders()
const { data } = await useAsyncData('notification-bell-unread', () =>
  $fetch<NotificationsResponse | null>('/api/portal/notifications', {
    headers,
    query: { status: 'unread', limit: 1 },
  }).catch(() => null))

const unread = computed(() => data.value?.unread ?? 0)
const badgeLabel = computed(() => (unread.value > 99 ? '99+' : String(unread.value)))
</script>

<template>
  <NuxtLink
    to="/notificacoes"
    class="relative inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-elevated hover:text-highlighted"
    :aria-label="unread > 0 ? `Notificações, ${unread} não lidas` : 'Notificações'"
  >
    <UIcon name="i-lucide-bell" class="h-5 w-5" />
    <span
      v-if="unread > 0"
      class="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-error px-1 text-[10px] font-bold leading-none text-white"
    >{{ badgeLabel }}</span>
  </NuxtLink>
</template>
