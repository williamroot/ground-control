<script setup lang="ts">
// Relatório executivo mensal (T-R18b.5, R18b do vídeo).
//
// *"Tenho um report executivo mensal aqui, que eu vou pegar, por exemplo, maio.
// Vou pegar aqui a DataStone… Aí, isso aqui eu consigo fazer em PDF."* (11:36)
//
// É o entregável recorrente: *"isso aqui, todo mês, a gente manda"* (10:51).
// Por isso a tela abre já no mês passado e com o cliente escolhível — o
// caminho de menor atrito para a tarefa que ele repete todo mês.
definePageMeta({ middleware: 'admin-auth' })

interface TenantSummary { id: string, trade_name: string, subdomain: string }

const headers = useRequestHeaders(['cookie'])

const { data: tenants } = await useAsyncData('admin-tenants-for-reports', () =>
  $fetch<TenantSummary[]>('/api/admin/tenants', { headers }).catch(() => []))

const tenantOptions = computed(() =>
  (tenants.value ?? []).map(t => ({ label: t.trade_name, value: t.id })))

const tenantId = ref<string>('')
const month = ref(previousMonth())

watchEffect(() => {
  if (!tenantId.value && tenantOptions.value.length) {
    tenantId.value = tenantOptions.value[0]!.value
  }
})

const monthValid = computed(() => isValidMonth(month.value))
const canQuery = computed(() => !!tenantId.value && monthValid.value)

const report = ref<MonthlyReport | null>(null)
const loading = ref(false)
const errorMsg = ref('')

async function load() {
  errorMsg.value = ''
  report.value = null
  // Mês inválido NÃO chega a virar chamada — o backend também recusa, mas o
  // operador não precisa de um round-trip para saber que digitou errado.
  if (!canQuery.value) {
    errorMsg.value = 'Escolha um cliente e um mês no formato AAAA-MM.'
    return
  }
  loading.value = true
  try {
    report.value = await $fetch<MonthlyReport>(
      `/api/admin/tenants/${tenantId.value}/reports/monthly?month=${month.value}`,
    )
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    if (err.statusCode === 422) errorMsg.value = 'Mês inválido.'
    else if (err.statusCode === 404) errorMsg.value = 'Cliente não encontrado.'
    else errorMsg.value = err.data?.detail || 'Falha ao gerar o relatório.'
  }
  finally {
    loading.value = false
  }
}

const pdfUrl = computed(() =>
  canQuery.value
    ? `/api/admin/tenants/${tenantId.value}/reports/monthly.pdf?month=${month.value}`
    : '')

const totalHours = computed(() =>
  (report.value?.tickets ?? []).reduce((acc, t) => acc + t.hours, 0))
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <header class="mb-6">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Relatório executivo
      </h1>
      <p class="mt-1 text-sm text-muted">
        Escolha o cliente e o mês. O mesmo conteúdo sai em PDF, com a marca do cliente.
      </p>
    </header>

    <UCard :ui="{ body: 'space-y-4' }">
      <div class="flex flex-wrap items-end gap-3">
        <UFormField label="Cliente" required>
          <USelect v-model="tenantId" :items="tenantOptions" class="w-64" />
        </UFormField>
        <UFormField label="Mês" required :error="month && !monthValid ? 'Formato AAAA-MM' : undefined">
          <UInput v-model="month" placeholder="2026-05" class="w-40" />
        </UFormField>
        <UButton color="primary" icon="i-lucide-file-text" :loading="loading" :disabled="!canQuery" @click="load">
          Gerar
        </UButton>
        <UButton
          v-if="report && !report.degraded"
          :to="pdfUrl"
          target="_blank"
          external
          color="neutral"
          variant="soft"
          icon="i-lucide-download"
        >
          Baixar PDF
        </UButton>
      </div>
      <p v-if="monthValid" class="text-xs text-muted">
        Período: {{ monthLabelPt(month) }}
      </p>
    </UCard>

    <UAlert
      v-if="errorMsg"
      class="mt-4"
      color="error"
      variant="soft"
      icon="i-lucide-alert-triangle"
      :title="errorMsg"
    />

    <template v-if="report">
      <UAlert
        v-if="report.degraded"
        class="mt-4"
        color="warning"
        variant="soft"
        icon="i-lucide-plug-zap"
        title="Znuny indisponível — relatório incompleto"
        description="Os chamados do período não puderam ser lidos. O consumo abaixo está correto, mas o PDF não é gerado enquanto o relatório estiver incompleto: um documento que vai para o cliente não pode parecer completo sem estar."
      />

      <section class="mt-8">
        <h2 class="mb-3 font-display text-base font-bold text-highlighted">
          Consumo em {{ report.month_label }}
        </h2>
        <div v-if="report.consumption.length" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <UCard v-for="c in report.consumption" :key="c.code" :ui="{ body: 'space-y-1' }">
            <p class="text-xs uppercase tracking-wide text-muted">{{ c.code }}</p>
            <p class="font-display text-2xl font-extrabold text-highlighted">
              {{ formatValue(c.kind, c.value) }}
            </p>
            <p class="text-xs text-muted">{{ c.unit_label }}</p>
          </UCard>
        </div>
        <UCard v-else class="text-sm text-muted">
          Nenhum contrato com consumo mensurável no período.
        </UCard>
        <p v-if="report.consumption.length > 1" class="mt-2 text-xs text-muted">
          Contratos de tipos diferentes — os valores não se somam.
        </p>
      </section>

      <section class="mt-8">
        <h2 class="mb-3 font-display text-base font-bold text-highlighted">
          Principais chamados por {{ report.dimension_label.toLowerCase() }}
        </h2>
        <UCard v-if="report.top_items.length" :ui="{ body: 'p-0' }">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-default text-left text-muted">
                <th class="px-4 py-2 font-medium">{{ report.dimension_label }}</th>
                <th class="px-4 py-2 text-right font-medium">Chamados</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in report.top_items" :key="it.label" class="border-b border-default/60">
                <td class="px-4 py-2 text-default">{{ it.label }}</td>
                <td class="px-4 py-2 text-right font-semibold text-highlighted">{{ it.count }}</td>
              </tr>
            </tbody>
          </table>
        </UCard>
        <UCard v-else class="text-sm text-muted">
          Nenhum chamado registrado no período.
        </UCard>
      </section>

      <section class="mt-8">
        <div class="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="font-display text-base font-bold text-highlighted">
            Chamados do período ({{ report.ticket_total }})
          </h2>
          <span class="text-xs text-muted">
            {{ totalHours.toFixed(2) }} h lançadas
          </span>
        </div>
        <UAlert
          v-if="report.tickets_truncated"
          class="mb-3"
          color="warning"
          variant="soft"
          icon="i-lucide-list-filter"
          title="Lista cortada"
          :description="`Mostrando os primeiros ${report.tickets.length} chamados. A contagem total (${report.ticket_total}) continua correta.`"
        />
        <div v-if="report.tickets.length" class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-default text-left text-muted">
                <th class="py-2 pr-3 font-medium">Número</th>
                <th class="py-2 pr-3 font-medium">Assunto</th>
                <th class="py-2 pr-3 font-medium">Aberto em</th>
                <th class="py-2 pr-3 font-medium">Estado</th>
                <th class="py-2 text-right font-medium">Horas</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in report.tickets" :key="t.znuny_ticket_id" class="border-b border-default/60">
                <td class="py-2 pr-3 font-mono text-xs text-default">{{ t.ticket_number }}</td>
                <td class="py-2 pr-3 text-highlighted">{{ t.title }}</td>
                <td class="py-2 pr-3 text-muted">{{ t.created.slice(0, 10) }}</td>
                <td class="py-2 pr-3 text-default">{{ t.state }}</td>
                <td class="py-2 text-right text-default">{{ t.hours.toFixed(2) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <UCard v-else class="text-sm text-muted">
          Nenhum chamado no período.
        </UCard>
      </section>
    </template>
  </div>
</template>
