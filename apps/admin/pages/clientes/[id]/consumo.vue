<script setup lang="ts">
// Consumo do cliente no console (T-R18a.3, R18a do vídeo).
//
// *"Se eu quero saber qual o consumo de cada cliente, eu venho aqui e pego esse
// cara e vejo nos últimos três meses qual foi o ciclo de utilização dele.
// Quando é contrato de hora, é hora. Quando é contrato de grana, aparece em
// formato de grana."* (11:00)
//
// O gráfico já existia — no PORTAL, sob o cookie do CLIENTE, contrato a
// contrato, cobrindo a vida inteira. O Kleber é agente da Gerti: para ver isso
// ele teria que entrar no portal de cada cliente. Esta tela é a mesma leitura,
// na superfície certa.
//
// **Um gráfico por unidade, nunca misturados** — é requisito, não estética.
definePageMeta({ middleware: 'admin-auth' })

interface TenantHeader { id: string, trade_name: string }

const route = useRoute()
const id = route.params.id as string
const headers = useRequestHeaders(['cookie'])

const { data: tenant } = await useAsyncData(`admin-tenant-head-c-${id}`, () =>
  $fetch<TenantHeader | null>(`/api/admin/tenants/${id}`, { headers }).catch(() => null))

// O seletor existe porque NÃO sabemos se "últimos três meses" é mês-calendário
// ou ciclo de faturamento (suposição S3). Deixar o operador escolher é melhor
// do que acertar por sorte — e transforma a dúvida em recurso.
const windowMode = ref<WindowMode | ''>('')
const count = ref(3)

const windowOptions = [
  { label: 'Padrão do sistema', value: '' },
  { label: 'Por ciclo de faturamento', value: 'cycles' },
  { label: 'Por mês-calendário', value: 'months' },
]
const countOptions = [3, 6, 12].map(n => ({ label: `${n} períodos`, value: n }))

const query = computed(() => {
  const p = new URLSearchParams()
  if (windowMode.value) p.set('window', windowMode.value)
  p.set('count', String(count.value))
  return p.toString()
})

const { data, pending, error, refresh } = await useAsyncData(
  `admin-tenant-consumo-${id}`,
  () => $fetch<ConsumptionSeriesResponse>(
    `/api/admin/tenants/${id}/consumption-series?${query.value}`,
    { headers },
  ),
  { watch: [query] },
)

const groups = computed(() => groupSeriesByKind(data.value?.series ?? []))
const isEmpty = computed(() => !pending.value && !error.value && groups.value.length === 0)

function barsFor(series: ContractSeries) {
  return series.points.map(p => ({ label: bucketLabel(p.bucket), value: p.value }))
}
function totalFor(series: ContractSeries) {
  return series.points.reduce((acc, p) => acc + p.value, 0)
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <ULink :to="`/clientes/${id}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <header class="mt-3 mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Consumo
        </h1>
        <p class="mt-1 text-sm text-muted">
          {{ tenant?.trade_name ?? 'Cliente' }}
        </p>
      </div>
      <div class="flex items-end gap-3">
        <UFormField label="Janela">
          <USelect v-model="windowMode" :items="windowOptions" class="w-56" />
        </UFormField>
        <UFormField label="Períodos">
          <USelect v-model="count" :items="countOptions" class="w-36" />
        </UFormField>
      </div>
    </header>

    <UCard v-if="pending" class="text-sm text-muted">
      Carregando consumo…
    </UCard>

    <UCard v-else-if="error" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Falha ao carregar o consumo
        </p>
        <UButton variant="soft" color="primary" @click="refresh()">
          Tentar de novo
        </UButton>
      </div>
    </UCard>

    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-chart-column" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Nada a exibir
        </p>
        <p class="max-w-md text-sm text-muted">
          Este cliente não tem contrato ativo com saldo mensurável. Contratos de
          valor fechado e SaaS não geram gráfico de consumo.
        </p>
      </div>
    </UCard>

    <div v-else class="space-y-6">
      <div v-for="g in groups" :key="g.kind" class="space-y-4">
        <div class="flex items-baseline gap-2">
          <h2 class="font-display text-base font-bold text-highlighted">
            Consumo em {{ g.kind === 'hours' ? 'horas' : g.kind === 'brl' ? 'reais' : 'atendimentos' }}
          </h2>
          <span class="text-xs text-muted">unidade: {{ unitLabel(g.kind) }}</span>
        </div>

        <UCard v-for="s in g.series" :key="s.contract_id" :ui="{ body: 'space-y-3' }">
          <div class="flex flex-wrap items-baseline justify-between gap-2">
            <p class="font-display text-sm font-bold text-highlighted">
              {{ s.code }}
            </p>
            <p class="text-sm text-muted">
              Total do período:
              <span class="font-semibold text-default">{{ formatValue(s.kind, totalFor(s)) }}</span>
            </p>
          </div>
          <BarChart :bars="barsFor(s)" />
          <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            <span v-for="p in s.points" :key="p.bucket">
              {{ bucketLabel(p.bucket) }}: <span class="text-default">{{ formatValue(s.kind, p.value) }}</span>
            </span>
          </div>
        </UCard>
      </div>

      <p v-if="groups.length > 1" class="text-xs text-muted">
        Este cliente tem contratos de tipos diferentes. Os gráficos acima estão
        separados por unidade de propósito — horas e reais não se somam.
      </p>
    </div>
  </div>
</template>
