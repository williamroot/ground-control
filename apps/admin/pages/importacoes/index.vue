<script setup lang="ts">
// Importação em lote (T-R8.4, R8).
//
// *"Quero importar cadastros, quero importar cliente, quero importar usuário
// do cliente."* (12:40) — e o contexto que dá o tamanho: a migração do TIFLUX
// são **60 clientes e 43 contratos**.
//
// O fluxo é obrigatoriamente: modelo → subir → **pré-visualizar** → confirmar.
// A pré-visualização não é conforto: importar 60 clientes e descobrir no 47º
// que a planilha tinha uma coluna trocada é o erro que ela evita.
definePageMeta({ middleware: 'admin-auth' })

interface TenantSummary { id: string, trade_name: string }

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const kind = ref<ImportKind>('tenants')
const tenantId = ref('')
const file = ref<File | null>(null)
const report = ref<ImportReport | null>(null)
const busy = ref(false)
const errorMsg = ref('')

const { data: tenants } = await useAsyncData('tenants-for-import', () =>
  $fetch<TenantSummary[]>('/api/admin/tenants', { headers }).catch(() => []))

const tenantOptions = computed(() => [
  { label: '— escolha o cliente —', value: '' },
  ...(tenants.value ?? []).map(t => ({ label: t.trade_name, value: t.id })),
])

const needsTenant = computed(() => kind.value === 'tenant_users')
const ready = computed(() => !!file.value && (!needsTenant.value || !!tenantId.value))

// Depois de importar, o relatório deixa de ser simulação — e o botão de
// confirmar precisa sumir, senão alguém importa duas vezes por engano.
const showRun = computed(() => canRun(report.value))

function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
  report.value = null
  errorMsg.value = ''
}

function reset() {
  file.value = null
  report.value = null
  errorMsg.value = ''
}

async function send(path: string) {
  if (!file.value) return null
  const form = new FormData()
  form.append('file', file.value)
  return await $fetch<ImportReport>(path, { method: 'POST', body: form })
}

async function simulate() {
  errorMsg.value = ''
  report.value = null
  busy.value = true
  try {
    report.value = await send(`/api/admin/import/${kind.value}/validate`)
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    errorMsg.value = err.data?.detail || 'Falha ao ler o arquivo.'
  }
  finally {
    busy.value = false
  }
}

const confirmOpen = ref(false)

async function run() {
  confirmOpen.value = false
  errorMsg.value = ''
  busy.value = true
  try {
    const qs = needsTenant.value ? `?tenant_id=${tenantId.value}` : ''
    report.value = await send(`/api/admin/import/${kind.value}${qs}`)
    if (report.value) {
      toast.add({ title: 'Importação concluída', description: summarize(report.value), color: 'success' })
    }
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    errorMsg.value = err.data?.detail || 'Falha na importação.'
  }
  finally {
    busy.value = false
  }
}

// Senhas geradas aparecem UMA vez. Depois desta tela, ninguém as recupera —
// nem nós: elas não são guardadas em lugar nenhum.
const generated = computed(() =>
  (report.value?.rows ?? []).filter(r => r.generated_password))
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <header class="mb-6">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Importações
      </h1>
      <p class="mt-1 text-sm text-muted">
        Carga em lote por planilha. Sempre com pré-visualização antes de gravar.
      </p>
    </header>

    <UCard :ui="{ body: 'space-y-4' }">
      <div class="flex flex-wrap items-end gap-3">
        <UFormField label="O que importar" required>
          <USelect v-model="kind" :items="IMPORT_KINDS" class="w-56" @update:model-value="reset" />
        </UFormField>
        <UFormField v-if="needsTenant" label="Cliente" required>
          <USelect v-model="tenantId" :items="tenantOptions" class="w-56" />
        </UFormField>
        <UButton
          :to="`/api/admin/import/${kind}/template`"
          external
          color="neutral"
          variant="soft"
          icon="i-lucide-download"
        >
          Baixar modelo
        </UButton>
      </div>

      <UFormField label="Arquivo CSV (UTF-8)" help="Máximo 5 MB / 2.000 linhas. Sem coluna de senha.">
        <input
          type="file"
          accept=".csv,text/csv"
          class="block w-full text-sm text-default file:mr-3 file:rounded-md file:border-0 file:bg-elevated file:px-3 file:py-2 file:text-sm"
          @change="onFile"
        >
      </UFormField>

      <div class="flex items-center gap-3">
        <UButton color="primary" icon="i-lucide-eye" :loading="busy" :disabled="!ready" @click="simulate">
          Pré-visualizar
        </UButton>
        <UButton
          v-if="showRun"
          color="success"
          icon="i-lucide-upload"
          :loading="busy"
          @click="confirmOpen = true"
        >
          Importar
        </UButton>
      </div>
    </UCard>

    <UAlert
      v-if="errorMsg"
      class="mt-4"
      color="error" variant="soft" icon="i-lucide-alert-triangle"
      title="Arquivo recusado"
      :description="errorMsg"
    />

    <template v-if="report">
      <UAlert
        class="mt-6"
        :color="report.dry_run ? 'info' : 'success'"
        variant="soft"
        :icon="report.dry_run ? 'i-lucide-eye' : 'i-lucide-check'"
        :title="report.dry_run ? 'Pré-visualização — nada foi gravado' : 'Importação concluída'"
        :description="summarize(report)"
      />

      <div v-if="generated.length" class="mt-4">
        <UAlert
          color="warning" variant="soft" icon="i-lucide-key"
          title="Senhas geradas — copie agora"
          description="Elas aparecem uma única vez. Nós não as guardamos em lugar nenhum; depois desta tela, só resetando."
        />
        <UCard class="mt-2" :ui="{ body: 'p-0' }">
          <table class="w-full text-sm">
            <tbody>
              <tr v-for="r in generated" :key="r.line" class="border-b border-default/60">
                <td class="px-4 py-2 text-default">{{ safeCell(r.key) }}</td>
                <td class="px-4 py-2 font-mono text-xs text-highlighted">{{ r.generated_password }}</td>
              </tr>
            </tbody>
          </table>
        </UCard>
      </div>

      <div class="mt-4 overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-default text-left text-muted">
              <th class="py-2 pr-3 font-medium">Linha</th>
              <th class="py-2 pr-3 font-medium">Registro</th>
              <th class="py-2 pr-3 font-medium">Situação</th>
              <th class="py-2 font-medium">Observação</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in report.rows" :key="r.line" class="border-b border-default/60">
              <td class="py-2 pr-3 font-mono text-xs text-muted">{{ r.line }}</td>
              <!-- Conteúdo de planilha é entrada não-confiável: texto puro, e
                   `safeCell` neutraliza o gatilho de fórmula do Excel. -->
              <td class="py-2 pr-3 text-default">{{ safeCell(r.key) }}</td>
              <td class="py-2 pr-3">
                <UBadge :color="STATUS_COLORS[r.status]" variant="subtle" size="sm">
                  {{ STATUS_LABELS[r.status] }}
                </UBadge>
              </td>
              <td class="py-2 text-muted">{{ safeCell(r.message) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <UModal v-model:open="confirmOpen" :title="confirmationLabel(report, kind)">
      <template #body>
        <p class="text-sm text-default">
          As linhas com problema serão puladas, e as que já existem não são duplicadas.
          A importação é idempotente: rodar o mesmo arquivo de novo não cria nada a mais.
        </p>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="ghost" color="neutral" @click="confirmOpen = false">Cancelar</UButton>
          <UButton color="success" :loading="busy" @click="run">Confirmar</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
