<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'
import {
  notificationAccentClass,
  notificationDotClass,
  notificationIconClass,
  notificationKindMeta,
} from '~/components/notification/labels'

// #3 V3 — central de notificações do cliente. Filtros Todas/Não lidas/Lidas,
// clique marca como lida e navega para `link_path` quando houver, "Marcar
// todas como lidas" só aparece quando há não lidas. `null` = falha (erro),
// `items: []` = vazio.
definePageMeta({ middleware: 'auth' })

interface NotificationItem {
  id: string
  kind: string
  title: string
  body: string | null
  link_path: string | null
  read_at: string | null
  created_at: string
}
interface NotificationsResponse {
  items: NotificationItem[]
  total: number
  unread: number
  limit: number
  offset: number
}

type FilterKey = 'all' | 'unread' | 'read'
const FILTERS: { key: FilterKey, label: string }[] = [
  { key: 'all', label: 'Todas' },
  { key: 'unread', label: 'Não lidas' },
  { key: 'read', label: 'Lidas' },
]

const headers = useSidecarHeaders()
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const filter = ref<FilterKey>('all')

const { data, pending, refresh } = await useAsyncData(
  'notifications-list',
  () =>
    $fetch<NotificationsResponse | null>('/api/portal/notifications', {
      headers,
      query: { status: filter.value },
    }).catch(() => null),
  { watch: [filter] },
)

const loadFailed = computed(() => !pending.value && data.value === null)
const items = computed(() => data.value?.items ?? [])
const isEmpty = computed(() => !pending.value && !loadFailed.value && items.value.length === 0)
const total = computed(() => data.value?.total ?? 0)
const unread = computed(() => data.value?.unread ?? 0)
const hasUnread = computed(() => unread.value > 0)

const markingId = ref<string | null>(null)
const markingAll = ref(false)

async function openNotification(item: NotificationItem) {
  if (!item.read_at) {
    markingId.value = item.id
    await $fetch(`/api/portal/notifications/${item.id}/read`, { method: 'POST' }).catch(() => null)
    markingId.value = null
    await refresh()
  }
  if (item.link_path) await navigateTo(item.link_path)
}

async function markAllAsRead() {
  markingAll.value = true
  await $fetch('/api/portal/notifications/read-all', { method: 'POST' }).catch(() => null)
  markingAll.value = false
  await refresh()
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
    + ' às ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

const emptyMessage = computed(() => {
  if (filter.value === 'unread') return 'Você não tem notificações não lidas.'
  if (filter.value === 'read') return 'Nenhuma notificação lida ainda.'
  return 'Você ainda não recebeu notificações.'
})
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-8">
    <header class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-sm text-muted">{{ tenantName }}</p>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Notificações
        </h1>
        <p class="mt-1 text-sm text-muted">
          {{ unread }} não lidas de {{ total }}
        </p>
      </div>
      <UButton
        v-if="hasUnread"
        color="neutral"
        variant="subtle"
        icon="i-lucide-check-check"
        label="Marcar todas como lidas"
        :loading="markingAll"
        @click="markAllAsRead"
      />
    </header>

    <div class="mb-6 inline-flex items-center gap-1 rounded-lg border border-default bg-default p-1" role="group" aria-label="Filtro de notificações">
      <button
        v-for="f in FILTERS"
        :key="f.key"
        type="button"
        class="rounded-md px-3 py-1.5 text-sm font-medium transition"
        :class="filter === f.key ? 'bg-elevated text-highlighted' : 'text-muted hover:text-highlighted'"
        @click="filter = f.key"
      >
        {{ f.label }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 4" :key="n" class="h-[72px] animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-4 py-10">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-error/10 text-error">
          <UIcon name="i-lucide-cloud-off" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar as notificações</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            As notificações estão indisponíveis no momento. Tente novamente em instantes.
          </p>
        </div>
        <UButton color="neutral" variant="subtle" icon="i-lucide-rotate-cw" label="Tentar novamente" @click="refresh()" />
      </div>
    </UCard>

    <!-- Vazio -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-4 py-12">
        <span
          class="inline-flex h-16 w-16 items-center justify-center rounded-2xl text-white shadow-sm"
          :style="{ background: 'linear-gradient(135deg, var(--brand-primary), var(--brand-accent))' }"
        >
          <UIcon name="i-lucide-bell-off" class="h-8 w-8" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Nada por aqui</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">{{ emptyMessage }}</p>
        </div>
      </div>
    </UCard>

    <!-- Lista -->
    <ul v-else class="space-y-3">
      <li v-for="n in items" :key="n.id">
        <button
          type="button"
          class="w-full rounded-xl border border-default px-4 py-3.5 text-left transition hover:border-highlighted"
          :class="[
            n.read_at ? 'bg-default opacity-60' : notificationAccentClass(n.kind),
          ]"
          :disabled="markingId === n.id"
          @click="openNotification(n)"
        >
          <div class="flex items-start gap-3">
            <span
              class="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
              :class="notificationIconClass(n.kind)"
            >
              <UIcon :name="notificationKindMeta(n.kind).icon" class="h-4 w-4" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <p class="font-medium text-highlighted" :class="{ 'font-semibold': !n.read_at }">
                  {{ n.title }}
                </p>
                <span
                  v-if="!n.read_at"
                  class="h-2 w-2 shrink-0 rounded-full"
                  :class="notificationDotClass(n.kind)"
                  aria-hidden="true"
                />
              </div>
              <p v-if="n.body" class="mt-0.5 line-clamp-2 text-sm text-muted">{{ n.body }}</p>
              <p class="mt-1 text-xs text-dimmed">{{ fmtDate(n.created_at) }}</p>
            </div>
          </div>
        </button>
      </li>
    </ul>
  </div>
</template>
