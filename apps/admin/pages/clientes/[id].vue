<script setup lang="ts">
import { statusColor, statusLabel, typeLabel } from '#shared/contracts'

definePageMeta({ middleware: 'admin-auth' })

interface Branding {
  display_name: string
  primary_color: string
  accent_color: string
  support_email?: string | null
  logo_url?: string | null
}
interface TenantUser { customer_login: string, role: string }
interface TenantContract { id: string, code: string, type: string, status: string }
interface TenantDetail {
  id: string
  legal_name: string
  trade_name: string
  document: string
  subdomain: string
  znuny_customer_id: string
  status: string
  branding: Branding | null
  users: TenantUser[]
  contracts: TenantContract[]
}

const route = useRoute()
const id = route.params.id as string
const headers = useRequestHeaders(['cookie'])
const { data: tenant } = await useAsyncData(`admin-tenant-${id}`, () =>
  $fetch<TenantDetail | null>(`/api/admin/tenants/${id}`, { headers }).catch(() => null))

const roleLabel = (r: string) =>
  r === 'admin' ? 'Administrador' : r === 'helpdesk' ? 'Helpdesk' : r
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <ULink to="/" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para clientes
    </ULink>

    <UCard v-if="!tenant" class="mt-6 text-center">
      <div class="flex flex-col items-center gap-3 py-12">
        <UIcon name="i-lucide-search-x" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Cliente não encontrado
        </p>
        <UButton to="/" variant="soft" color="primary">
          Voltar à lista
        </UButton>
      </div>
    </UCard>

    <template v-else>
      <header class="mt-3 mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="flex items-center gap-3">
            <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
              {{ tenant.trade_name }}
            </h1>
            <UBadge :color="statusColor(tenant.status)" variant="soft">
              {{ statusLabel(tenant.status) }}
            </UBadge>
          </div>
          <p class="mt-1 text-sm text-muted">
            {{ tenant.legal_name }} · {{ tenant.subdomain }}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <UButton
            :to="`/clientes/${tenant.id}/faturas`"
            color="neutral"
            variant="soft"
            icon="i-lucide-receipt"
          >
            Faturas
          </UButton>
          <UButton
            :to="`/clientes/${tenant.id}/contratos/novo`"
            color="primary"
            icon="i-lucide-plus"
          >
            Novo contrato
          </UButton>
        </div>
      </header>

      <div class="grid gap-6 lg:grid-cols-2">
        <UCard :ui="{ body: 'space-y-3' }">
          <h2 class="font-display text-base font-bold text-highlighted">
            Dados cadastrais
          </h2>
          <dl class="space-y-2 text-sm">
            <div class="flex justify-between gap-4">
              <dt class="text-muted">Razão social</dt>
              <dd class="text-right text-default">{{ tenant.legal_name }}</dd>
            </div>
            <div class="flex justify-between gap-4">
              <dt class="text-muted">Documento</dt>
              <dd class="text-right text-default">{{ tenant.document }}</dd>
            </div>
            <div class="flex justify-between gap-4">
              <dt class="text-muted">Subdomínio</dt>
              <dd class="text-right text-default">{{ tenant.subdomain }}</dd>
            </div>
            <div class="flex justify-between gap-4">
              <dt class="text-muted">Znuny ID</dt>
              <dd class="text-right text-default">{{ tenant.znuny_customer_id }}</dd>
            </div>
          </dl>
        </UCard>

        <UCard v-if="tenant.branding" :ui="{ body: 'space-y-3' }">
          <h2 class="font-display text-base font-bold text-highlighted">
            Branding do portal
          </h2>
          <dl class="space-y-2 text-sm">
            <div class="flex justify-between gap-4">
              <dt class="text-muted">Nome de exibição</dt>
              <dd class="text-right text-default">{{ tenant.branding.display_name }}</dd>
            </div>
            <div class="flex items-center justify-between gap-4">
              <dt class="text-muted">Cor primária</dt>
              <dd class="flex items-center gap-2 text-default">
                <span class="inline-block h-4 w-4 rounded border border-default" :style="{ background: tenant.branding.primary_color }" />
                {{ tenant.branding.primary_color }}
              </dd>
            </div>
            <div class="flex items-center justify-between gap-4">
              <dt class="text-muted">Cor de destaque</dt>
              <dd class="flex items-center gap-2 text-default">
                <span class="inline-block h-4 w-4 rounded border border-default" :style="{ background: tenant.branding.accent_color }" />
                {{ tenant.branding.accent_color }}
              </dd>
            </div>
            <div v-if="tenant.branding.support_email" class="flex justify-between gap-4">
              <dt class="text-muted">E-mail de suporte</dt>
              <dd class="text-right text-default">{{ tenant.branding.support_email }}</dd>
            </div>
          </dl>
        </UCard>
      </div>

      <section class="mt-6">
        <h2 class="mb-3 font-display text-base font-bold text-highlighted">
          Usuários
        </h2>
        <UCard v-if="tenant.users.length === 0" class="text-sm text-muted">
          Nenhum usuário cadastrado.
        </UCard>
        <div v-else class="grid gap-3 sm:grid-cols-2">
          <UCard v-for="u in tenant.users" :key="u.customer_login" :ui="{ body: 'flex items-center justify-between gap-3' }">
            <span class="truncate text-sm text-default">{{ u.customer_login }}</span>
            <UBadge color="primary" variant="subtle" size="sm">{{ roleLabel(u.role) }}</UBadge>
          </UCard>
        </div>
      </section>

      <section class="mt-6">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="font-display text-base font-bold text-highlighted">
            Contratos
          </h2>
          <UButton
            :to="`/clientes/${tenant.id}/contratos/novo`"
            variant="soft"
            color="primary"
            icon="i-lucide-plus"
            size="sm"
          >
            Novo contrato
          </UButton>
        </div>
        <UCard v-if="tenant.contracts.length === 0" class="text-sm text-muted">
          Nenhum contrato ainda. Crie o primeiro contrato deste cliente.
        </UCard>
        <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <UCard v-for="c in tenant.contracts" :key="c.id" :ui="{ body: 'space-y-2' }">
            <div class="flex items-start justify-between gap-2">
              <p class="font-display text-sm font-bold text-highlighted">{{ c.code }}</p>
              <UBadge :color="statusColor(c.status)" variant="soft" size="sm">{{ statusLabel(c.status) }}</UBadge>
            </div>
            <UBadge color="primary" variant="subtle" size="sm">{{ typeLabel(c.type) }}</UBadge>
          </UCard>
        </div>
      </section>
    </template>
  </div>
</template>
