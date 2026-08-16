<script setup lang="ts">
// Relacionamentos: quais filas o cliente acessa, e qual é a padrão (T-R5.4, R5).
//
// *"Aqui a gente vai falar quais filas de atendimento o cara vai ter acesso.
// Então a gente tem uma fila padrão. Tudo que entra por e-mail vem pra essa
// fila."* (04:03)
//
// A limitação vale ser dita na própria tela: a restrição é da NOSSA camada
// (portal e API). Um agente logado direto no painel do Znuny não a enxerga.
definePageMeta({ middleware: 'admin-auth' })

interface TenantHeader { id: string, trade_name: string }
interface QueuesResponse { queues: TenantQueue[] }
interface ZnunyQueueRow { ID?: number, Name?: string, GroupID?: number, ValidID?: number }
interface ZnunyListResponse { items?: ZnunyQueueRow[], support?: { GroupList?: Record<string, string> } }

const route = useRoute()
const id = route.params.id as string
const headers = useRequestHeaders(['cookie'])

const { data: tenant } = await useAsyncData(`admin-tenant-head-q-${id}`, () =>
  $fetch<TenantHeader | null>(`/api/admin/tenants/${id}`, { headers }).catch(() => null))

const { data: current, pending, error, refresh } = await useAsyncData(
  `admin-tenant-queues-${id}`,
  () => $fetch<QueuesResponse>(`/api/admin/tenants/${id}/queues`, { headers }),
)

// Lista viva de filas do Znuny — é dela que sai a multi-seleção.
const { data: live, error: liveError } = await useAsyncData('admin-znuny-queues', () =>
  $fetch<ZnunyListResponse>('/api/admin/znuny/objects/Queue', { headers }).catch(() => null))

const options = computed<QueueOption[]>(() => {
  const groups = live.value?.support?.GroupList ?? {}
  return (live.value?.items ?? [])
    .filter(q => q.ID !== undefined && q.ValidID === 1)
    .map(q => ({
      id: Number(q.ID),
      name: String(q.Name ?? q.ID),
      group_id: q.GroupID ?? null,
      group_name: q.GroupID !== undefined ? (groups[String(q.GroupID)] ?? null) : null,
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'))
})

const selection = ref<QueueSelection[]>([])
watchEffect(() => {
  if (current.value) selection.value = selectionFromTenantQueues(current.value.queues)
})

const errors = computed(() => validateQueueSelection(selection.value))
const isSelected = (qid: number) => selection.value.some(s => s.id === qid)
const isDefault = (qid: number) => selection.value.some(s => s.id === qid && s.is_default)

const pendingRemoveDefault = ref<QueueOption | null>(null)

function onToggle(q: QueueOption) {
  // Tirar a fila PADRÃO muda onde os chamados novos deste cliente vão cair —
  // pede confirmação, não é clique de rotina (invariante 3).
  if (isDefault(q.id)) { pendingRemoveDefault.value = q; return }
  selection.value = toggleQueue(selection.value, q.id)
}

function confirmRemoveDefault() {
  if (!pendingRemoveDefault.value) return
  selection.value = toggleQueue(selection.value, pendingRemoveDefault.value.id)
  pendingRemoveDefault.value = null
}

function onSetDefault(q: QueueOption) {
  if (!isSelected(q.id)) selection.value = toggleQueue(selection.value, q.id)
  selection.value = setDefault(selection.value, q.id)
}

const saving = ref(false)
const saveError = ref('')
const savedMsg = ref('')

async function save() {
  saveError.value = ''
  savedMsg.value = ''
  if (errors.value.length) return
  saving.value = true
  try {
    await $fetch(`/api/admin/tenants/${id}/queues`, {
      method: 'PUT',
      body: buildQueuesPayload(selection.value),
    })
    savedMsg.value = 'Filas atualizadas.'
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    if (err.statusCode === 422) saveError.value = err.data?.detail || 'Seleção recusada.'
    else if (err.statusCode === 503) saveError.value = 'Znuny indisponível — nada foi gravado.'
    else saveError.value = err.data?.detail || 'Falha ao salvar. Tente novamente.'
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-5 py-10">
    <ULink :to="`/clientes/${id}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <header class="mt-3 mb-6">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Relacionamentos
      </h1>
      <p class="mt-1 text-sm text-muted">
        {{ tenant?.trade_name ?? 'Cliente' }} · filas de atendimento
      </p>
    </header>

    <UAlert
      class="mb-4"
      color="neutral"
      variant="soft"
      icon="i-lucide-info"
      title="A restrição vale no portal e na API do Ground Control"
      description="Um agente logado diretamente na interface do Znuny continua enxergando todas as filas — esta configuração não muda as permissões nativas."
    />

    <UCard v-if="pending" class="text-sm text-muted">
      Carregando filas…
    </UCard>

    <UCard v-else-if="error" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Falha ao carregar as filas deste cliente
        </p>
        <UButton variant="soft" color="primary" @click="refresh()">
          Tentar de novo
        </UButton>
      </div>
    </UCard>

    <UCard v-else-if="liveError || options.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-inbox" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Nenhuma fila disponível no Znuny
        </p>
        <p class="max-w-md text-sm text-muted">
          Cadastre as filas de atendimento primeiro; depois volte aqui para dizer
          quais delas este cliente acessa.
        </p>
        <UButton to="/znuny/filas" variant="soft" color="primary" icon="i-lucide-list">
          Cadastrar filas no Znuny
        </UButton>
      </div>
    </UCard>

    <template v-else>
      <UAlert
        v-if="saveError"
        class="mb-4"
        color="error"
        variant="soft"
        icon="i-lucide-alert-triangle"
        :title="saveError"
      />
      <UAlert
        v-if="savedMsg"
        class="mb-4"
        color="success"
        variant="soft"
        icon="i-lucide-check"
        :title="savedMsg"
      />
      <UAlert
        v-if="errors.length"
        class="mb-4"
        color="warning"
        variant="soft"
        icon="i-lucide-alert-triangle"
        title="Ajuste antes de salvar"
      >
        <template #description>
          <ul class="list-disc space-y-0.5 pl-5">
            <li v-for="e in errors" :key="e">{{ e }}</li>
          </ul>
        </template>
      </UAlert>

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-default text-left text-muted">
              <th class="py-2 pr-3 font-medium">Acessa</th>
              <th class="py-2 pr-3 font-medium">Fila</th>
              <th class="py-2 pr-3 font-medium">Atendida por</th>
              <th class="py-2 font-medium">Padrão</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in options" :key="q.id" class="border-b border-default/60">
              <td class="py-3 pr-3">
                <UCheckbox :model-value="isSelected(q.id)" @update:model-value="onToggle(q)" />
              </td>
              <td class="py-3 pr-3 font-medium text-highlighted">
                {{ q.name }}
              </td>
              <td class="py-3 pr-3 text-default">
                {{ servedByLabel(q.group_name, null) }}
              </td>
              <td class="py-3">
                <UBadge v-if="isDefault(q.id)" color="primary" variant="solid" size="sm">
                  Padrão
                </UBadge>
                <UButton
                  v-else
                  size="xs"
                  variant="ghost"
                  color="neutral"
                  icon="i-lucide-star"
                  @click="onSetDefault(q)"
                >
                  Tornar padrão
                </UButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mt-6 flex items-center gap-3">
        <UButton
          color="primary"
          size="lg"
          icon="i-lucide-save"
          :loading="saving"
          :disabled="errors.length > 0"
          @click="save"
        >
          Salvar
        </UButton>
        <UButton :to="`/clientes/${id}`" variant="ghost" color="neutral" :disabled="saving">
          Cancelar
        </UButton>
      </div>
    </template>

    <UModal
      :open="pendingRemoveDefault !== null"
      title="Remover a fila padrão?"
      @update:open="(v: boolean) => { if (!v) pendingRemoveDefault = null }"
    >
      <template #body>
        <p class="text-sm text-default">
          <strong>{{ pendingRemoveDefault?.name }}</strong> é a fila padrão deste cliente.
          Removendo-a, os chamados novos deixam de cair nela — e, enquanto você não
          marcar outra como padrão, voltam para a fila de triagem do Znuny.
        </p>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="ghost" color="neutral" @click="pendingRemoveDefault = null">
            Cancelar
          </UButton>
          <UButton color="error" @click="confirmRemoveDefault">
            Remover
          </UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
