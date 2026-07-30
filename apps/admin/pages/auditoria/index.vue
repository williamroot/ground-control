<script setup lang="ts">
// Trilha de auditoria (Spec #3, V5) — busca textual + filtro de ação + filtro
// de cliente + período + paginação real (limit/offset, máx. 200). Rótulos e
// cores semânticas em shared/audit.ts (testado sem Nuxt).
import { actionColor, actionLabel, actorLabel, AUDIT_ACTIONS, DEFAULT_AUDIT_LIMIT, entityLabel } from '#shared/audit'

definePageMeta({ middleware: 'admin-auth' })

interface TenantSummary { id: string, trade_name: string }
interface AuditLogItem {
  id: string
  at: string
  actor_type: string
  actor_login: string | null
  tenant_id: string | null
  action: string
  entity: string
  entity_id: string | null
  description: string
}
interface AuditLogResponse { items: AuditLogItem[], total: number, limit: number, offset: number }

const headers = useRequestHeaders(['cookie'])

const { data: tenants } = await useAsyncData('auditoria-tenants', () =>
  $fetch<TenantSummary[]>('/api/admin/tenants', { headers }).catch(() => [] as TenantSummary[]))

const ALL = '__all__'
const actionOptions = [{ label: 'Todas', value: ALL }, ...AUDIT_ACTIONS.map(a => ({ label: actionLabel(a), value: a }))]
const tenantOptions = computed(() => [
  { label: 'Todos os clientes', value: ALL },
  ...(tenants.value ?? []).map(t => ({ label: t.trade_name, value: t.id })),
])

const q = ref('')
const action = ref<string>(ALL)
const tenantId = ref<string>(ALL)
const from = ref('')
const to = ref('')
const limit = ref(DEFAULT_AUDIT_LIMIT)
const offset = ref(0)

// Debounce leve na busca textual para não disparar uma request por tecla.
const debouncedQ = ref('')
let qTimer: ReturnType<typeof setTimeout> | undefined
watch(q, (value) => {
  if (qTimer) clearTimeout(qTimer)
  qTimer = setTimeout(() => { debouncedQ.value = value }, 300)
})

// Qualquer mudança de filtro volta para a primeira página.
watch([debouncedQ, action, tenantId, from, to], () => { offset.value = 0 })

const { data: result, pending, refresh } = await useAsyncData<AuditLogResponse | null>(
  'auditoria-logs',
  () => {
    const query: Record<string, string | number> = { limit: limit.value, offset: offset.value }
    if (debouncedQ.value.trim()) query.q = debouncedQ.value.trim()
    if (action.value !== ALL) query.action = action.value
    if (tenantId.value !== ALL) query.tenant_id = tenantId.value
    if (from.value) query.from = from.value
    if (to.value) query.to = to.value
    return $fetch<AuditLogResponse>('/api/admin/audit-logs', { headers, query }).catch(() => null)
  },
  { watch: [debouncedQ, action, tenantId, from, to, offset] },
)

const loadFailed = computed(() => !pending.value && result.value === null)
const items = computed(() => result.value?.items ?? [])
const isEmpty = computed(() => !pending.value && !loadFailed.value && items.value.length === 0)

const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => {
  const total = result.value?.total ?? 0
  return offset.value + limit.value < total
})
function prevPage() { if (canPrev.value) offset.value = Math.max(0, offset.value - limit.value) }
function nextPage() { if (canNext.value) offset.value += limit.value }

function fmtAt(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR')
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <header class="mb-6">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Trilha de auditoria
      </h1>
      <p class="mt-1 text-sm text-muted">
        Ações registradas no console e nas integrações — quem fez o quê, quando e em qual cliente.
      </p>
    </header>

    <UCard class="mb-6" :ui="{ body: 'grid gap-3 sm:grid-cols-2 lg:grid-cols-5' }">
      <UFormField label="Buscar">
        <UInput v-model="q" placeholder="ator, entidade, descrição…" icon="i-lucide-search" class="w-full" />
      </UFormField>
      <UFormField label="Ação">
        <USelect v-model="action" :items="actionOptions" class="w-full" />
      </UFormField>
      <UFormField label="Cliente">
        <USelect v-model="tenantId" :items="tenantOptions" class="w-full" />
      </UFormField>
      <UFormField label="De">
        <UInput v-model="from" type="date" class="w-full" />
      </UFormField>
      <UFormField label="Até">
        <UInput v-model="to" type="date" class="w-full" />
      </UFormField>
    </UCard>

    <div v-if="pending" class="space-y-3">
      <div v-for="n in 5" :key="n" class="h-12 animate-pulse rounded-lg border border-default bg-elevated" />
    </div>

    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar</p>
        <p class="max-w-sm text-sm text-muted">Falha ao buscar a trilha de auditoria. Tente novamente.</p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refresh">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-scroll-text" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nenhum registro encontrado</p>
        <p class="max-w-sm text-sm text-muted">Ajuste os filtros acima ou tente um período diferente.</p>
      </div>
    </UCard>

    <template v-else>
      <div class="overflow-hidden rounded-lg border border-default">
        <table class="w-full text-sm">
          <thead class="bg-muted text-left text-xs uppercase text-muted">
            <tr>
              <th class="px-4 py-2 font-medium">Data/Hora</th>
              <th class="px-4 py-2 font-medium">Ator</th>
              <th class="px-4 py-2 font-medium">Ação</th>
              <th class="px-4 py-2 font-medium">Entidade</th>
              <th class="px-4 py-2 font-medium">Descrição</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-default">
            <tr v-for="log in items" :key="log.id" class="hover:bg-elevated/50">
              <td class="whitespace-nowrap px-4 py-2.5 text-muted">{{ fmtAt(log.at) }}</td>
              <td class="px-4 py-2.5 text-default">{{ actorLabel(log.actor_type, log.actor_login) }}</td>
              <td class="px-4 py-2.5">
                <UBadge :color="actionColor(log.action)" variant="soft" size="sm">
                  {{ actionLabel(log.action) }}
                </UBadge>
              </td>
              <td class="px-4 py-2.5 font-mono text-xs text-muted">{{ entityLabel(log.entity, log.entity_id) }}</td>
              <td class="px-4 py-2.5 text-default">{{ log.description }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mt-4 flex items-center justify-between text-sm text-muted">
        <span>{{ result?.total ?? 0 }} registro(s) — mostrando {{ offset + 1 }}–{{ offset + items.length }}</span>
        <div class="flex gap-2">
          <UButton size="sm" variant="soft" color="neutral" icon="i-lucide-chevron-left" :disabled="!canPrev" @click="prevPage">
            Anterior
          </UButton>
          <UButton size="sm" variant="soft" color="neutral" trailing-icon="i-lucide-chevron-right" :disabled="!canNext" @click="nextPage">
            Próxima
          </UButton>
        </div>
      </div>
    </template>
  </div>
</template>
