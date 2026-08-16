<script setup lang="ts">
// Chamados do cliente, na ficha (T-R1.6, aceite A1.5).
//
// *"Aqui eu consigo ver os tickets desse cliente"* (02:59). O backend já sabia
// filtrar por cliente desde o #1J; faltava a tela — o operador tinha que ir
// para /atendimento e procurar.
definePageMeta({ middleware: 'admin-auth' })

interface TenantHeader { id: string, trade_name: string }
interface AdminTicket {
  znuny_ticket_id: number
  ticket_number?: string
  title?: string
  state?: string
  created?: string
  customer_user?: string
  contract?: { code: string, type: string } | null
}

const route = useRoute()
const id = route.params.id as string
const headers = useRequestHeaders(['cookie'])

const { data: tenant } = await useAsyncData(`admin-tenant-head-t-${id}`, () =>
  $fetch<TenantHeader | null>(`/api/admin/tenants/${id}`, { headers }).catch(() => null))

const { data: tickets, pending, error, refresh } = await useAsyncData(
  `admin-tenant-tickets-${id}`,
  () => $fetch<AdminTicket[]>(`/api/admin/tenants/${id}/tickets`, { headers }),
)

const rows = computed(() => tickets.value ?? [])
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <ULink :to="`/clientes/${id}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <header class="mt-3 mb-6">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Chamados
      </h1>
      <p class="mt-1 text-sm text-muted">
        {{ tenant?.trade_name ?? 'Cliente' }}
      </p>
    </header>

    <UCard v-if="pending" class="text-sm text-muted">
      Carregando chamados…
    </UCard>

    <UCard v-else-if="error" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Falha ao carregar os chamados
        </p>
        <p class="max-w-md text-sm text-muted">
          A busca depende do Znuny estar respondendo.
        </p>
        <UButton variant="soft" color="primary" @click="refresh()">
          Tentar de novo
        </UButton>
      </div>
    </UCard>

    <UCard v-else-if="rows.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-ticket" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Nenhum chamado deste cliente
        </p>
        <p class="max-w-md text-sm text-muted">
          Quando alguém abrir um chamado pelo portal ou por e-mail, ele aparece aqui.
        </p>
      </div>
    </UCard>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-default text-left text-muted">
            <th class="py-2 pr-3 font-medium">Número</th>
            <th class="py-2 pr-3 font-medium">Assunto</th>
            <th class="py-2 pr-3 font-medium">Solicitante</th>
            <th class="py-2 pr-3 font-medium">Contrato</th>
            <th class="py-2 pr-3 font-medium">Estado</th>
            <th class="py-2 font-medium">Aberto em</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in rows" :key="t.znuny_ticket_id" class="border-b border-default/60">
            <td class="py-3 pr-3 font-mono text-xs text-default">
              {{ t.ticket_number || t.znuny_ticket_id }}
            </td>
            <td class="py-3 pr-3 font-medium text-highlighted">
              {{ t.title || '—' }}
            </td>
            <td class="py-3 pr-3 text-default">
              {{ t.customer_user || '—' }}
            </td>
            <td class="py-3 pr-3">
              <UBadge v-if="t.contract" color="primary" variant="subtle" size="sm">
                {{ t.contract.code }}
              </UBadge>
              <UBadge v-else color="warning" variant="subtle" size="sm">
                sem contrato
              </UBadge>
            </td>
            <td class="py-3 pr-3 text-default">{{ t.state || '—' }}</td>
            <td class="py-3 text-muted">{{ t.created || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
