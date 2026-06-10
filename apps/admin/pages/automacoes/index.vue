<script setup lang="ts">
// Automações (#1Q) — lista de regras por tenant. Seleciona o cliente, lista as
// regras (nome, gatilho, ativa) e leva ao editor. H8 nas cores (sem cor de marca
// para semântica de status). A execução é no evento real (não há "aplicar agora").
definePageMeta({ middleware: 'admin-auth' })

interface TenantSummary {
  id: string
  trade_name: string
  subdomain: string
}

interface RuleRow {
  id: string
  name: string
  trigger_event: string
  position: number
  enabled: boolean
  conditions: unknown[]
  actions: unknown[]
}

const headers = useRequestHeaders(['cookie'])
const { data: tenants } = await useAsyncData('admin-tenants-automation', () =>
  $fetch<TenantSummary[]>('/api/admin/tenants', { headers })
    .catch(() => [] as TenantSummary[]))

const selectedTenant = ref<string>('')
watchEffect(() => {
  if (!selectedTenant.value && tenants.value?.length) {
    selectedTenant.value = tenants.value[0]!.id
  }
})

const rules = ref<RuleRow[]>([])
const loading = ref(false)

async function loadRules() {
  if (!selectedTenant.value) return
  loading.value = true
  try {
    rules.value = await $fetch<RuleRow[]>(
      `/api/admin/tenants/${selectedTenant.value}/automation-rules`,
    ).catch(() => [])
  }
  finally {
    loading.value = false
  }
}
watch(selectedTenant, loadRules, { immediate: true })

const tenantOptions = computed(() =>
  (tenants.value ?? []).map(t => ({ label: t.trade_name, value: t.id })),
)
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <header class="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Automações
        </h1>
        <p class="mt-1 text-sm text-muted">
          Regras no-code de triagem/escalonamento. Disparam em eventos reais de ticket.
        </p>
      </div>
      <UButton
        v-if="selectedTenant"
        :to="`/automacoes/novo?tenant=${selectedTenant}`"
        color="primary"
        icon="i-lucide-plus"
      >
        Nova regra
      </UButton>
    </header>

    <div class="mb-6 max-w-xs">
      <label class="mb-1 block text-xs font-medium text-muted">Cliente</label>
      <USelect v-model="selectedTenant" :items="tenantOptions" placeholder="Selecione um cliente" />
    </div>

    <UCard v-if="!loading && rules.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-12">
        <p class="font-display text-lg font-semibold text-highlighted">
          Nenhuma regra ainda
        </p>
        <p class="max-w-sm text-sm text-muted">
          Crie a primeira regra de automação para este cliente.
        </p>
        <UButton
          v-if="selectedTenant"
          :to="`/automacoes/novo?tenant=${selectedTenant}`"
          color="primary"
          icon="i-lucide-plus"
          class="mt-1"
        >
          Nova regra
        </UButton>
      </div>
    </UCard>

    <div v-else class="overflow-hidden rounded-lg border border-default">
      <table class="w-full text-sm">
        <thead class="bg-muted text-left text-xs uppercase text-muted">
          <tr>
            <th class="px-4 py-2 font-medium">Nome</th>
            <th class="px-4 py-2 font-medium">Gatilho</th>
            <th class="px-4 py-2 font-medium">Ordem</th>
            <th class="px-4 py-2 font-medium">Status</th>
            <th class="px-4 py-2" />
          </tr>
        </thead>
        <tbody class="divide-y divide-default">
          <tr v-for="r in rules" :key="r.id" class="hover:bg-elevated/50">
            <td class="px-4 py-2.5 font-medium text-highlighted">{{ r.name }}</td>
            <td class="px-4 py-2.5 text-muted">{{ r.trigger_event }}</td>
            <td class="px-4 py-2.5 text-muted">{{ r.position }}</td>
            <td class="px-4 py-2.5">
              <UBadge :color="r.enabled ? 'success' : 'neutral'" variant="soft" size="sm">
                {{ r.enabled ? 'ativa' : 'desativada' }}
              </UBadge>
            </td>
            <td class="px-4 py-2.5 text-right">
              <UButton
                :to="`/automacoes/${r.id}?tenant=${selectedTenant}`"
                color="neutral"
                variant="ghost"
                size="xs"
                icon="i-lucide-pencil"
              >
                Editar
              </UButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
