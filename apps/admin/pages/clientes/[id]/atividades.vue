<script setup lang="ts">
// Atividades recorrentes do cliente (T-R11.4/11.5, R11).
//
// *"Verificação de backup, verificação de patches, vulnerabilidades… É uma
// agenda. Isso é importante também, porque é o dia a dia dos técnicos."* (07:09)
//
// Duas visões na mesma tela, porque servem a duas perguntas diferentes: o
// CADASTRO ("o que está agendado?") e a AGENDA ("o que vem pela frente?").
definePageMeta({ middleware: 'admin-auth' })

interface TenantHeader { id: string, trade_name: string }
interface ContractRow { id: string, code: string, status: string }

const route = useRoute()
const id = route.params.id as string
const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const view = ref<'cadastro' | 'agenda'>('cadastro')
const views = [
  { value: 'cadastro', label: 'Atividades' },
  { value: 'agenda', label: 'Próximos 30 dias' },
]

const { data: tenant } = await useAsyncData(`admin-tenant-head-a-${id}`, () =>
  $fetch<TenantHeader | null>(`/api/admin/tenants/${id}`, { headers }).catch(() => null))

const { data: tasks, pending, error, refresh } = await useAsyncData(
  `admin-recurring-${id}`,
  () => $fetch<RecurringTask[]>(`/api/admin/tenants/${id}/recurring-tasks`, { headers }),
)

const { data: agenda, refresh: refreshAgenda } = await useAsyncData(
  `admin-recurring-agenda-${id}`,
  () => $fetch<AgendaEntry[]>(`/api/admin/tenants/${id}/recurring-tasks/agenda?days=30`, { headers }),
)

const { data: detail } = await useAsyncData(`admin-tenant-contracts-${id}`, () =>
  $fetch<{ contracts?: ContractRow[] }>(`/api/admin/tenants/${id}`, { headers }).catch(() => null))

const contractOptions = computed(() => [
  { label: '— não consome contrato —', value: '' },
  ...(detail.value?.contracts ?? [])
    .filter(c => c.status === 'active')
    .map(c => ({ label: c.code, value: c.id })),
])

const grouped = computed(() => groupAgendaByDate(agenda.value ?? []))

const open = ref(false)
const editingId = ref<string | null>(null)
const draft = reactive(emptyRecurringDraft())
const formErrors = ref<string[]>([])
const saving = ref(false)
const saveError = ref('')

const monthWarning = computed(() => shortMonthWarning(draft))

function openNew() {
  Object.assign(draft, emptyRecurringDraft())
  editingId.value = null
  formErrors.value = []
  saveError.value = ''
  open.value = true
}
function openEdit(t: RecurringTask) {
  Object.assign(draft, draftFromTask(t))
  editingId.value = t.id
  formErrors.value = []
  saveError.value = ''
  open.value = true
}

async function save() {
  saveError.value = ''
  formErrors.value = validateRecurringDraft(draft)
  if (formErrors.value.length) return
  saving.value = true
  try {
    const body = buildRecurringPayload(draft)
    if (editingId.value) {
      await $fetch(`/api/admin/tenants/${id}/recurring-tasks/${editingId.value}`, { method: 'PUT', body })
    }
    else {
      await $fetch(`/api/admin/tenants/${id}/recurring-tasks`, { method: 'POST', body })
    }
    open.value = false
    await Promise.all([refresh(), refreshAgenda()])
    toast.add({ title: 'Atividade salva', color: 'success' })
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    saveError.value = err.data?.detail || 'Falha ao salvar a atividade.'
  }
  finally {
    saving.value = false
  }
}

async function toggleActive(t: RecurringTask) {
  const body = buildRecurringPayload({ ...draftFromTask(t), active: !t.active })
  await $fetch(`/api/admin/tenants/${id}/recurring-tasks/${t.id}`, { method: 'PUT', body })
  await Promise.all([refresh(), refreshAgenda()])
}

const dateLabel = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString('pt-BR', {
    weekday: 'long', day: '2-digit', month: 'short',
  })
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
          Atividades recorrentes
        </h1>
        <p class="mt-1 text-sm text-muted">
          {{ tenant?.trade_name ?? 'Cliente' }} — o que vira chamado sozinho, e quando.
        </p>
      </div>
      <UButton color="primary" icon="i-lucide-calendar-plus" @click="openNew">
        Nova atividade
      </UButton>
    </header>

    <UTabs v-model="view" :items="views" class="mb-6" />

    <!-- cadastro -->
    <section v-if="view === 'cadastro'">
      <UCard v-if="pending" class="text-sm text-muted">Carregando…</UCard>
      <UCard v-else-if="error" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
          <p class="font-display text-lg font-semibold text-highlighted">Falha ao carregar</p>
          <UButton variant="soft" color="primary" @click="refresh()">Tentar de novo</UButton>
        </div>
      </UCard>
      <UCard v-else-if="!tasks?.length" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-calendar-clock" class="h-10 w-10 text-muted" />
          <p class="font-display text-lg font-semibold text-highlighted">
            Nenhuma atividade agendada
          </p>
          <p class="max-w-md text-sm text-muted">
            Verificação de backup, patches, vulnerabilidades — o que a equipe faz toda
            semana e hoje ninguém lembra de abrir.
          </p>
          <UButton color="primary" icon="i-lucide-calendar-plus" @click="openNew">
            Criar a primeira
          </UButton>
        </div>
      </UCard>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-default text-left text-muted">
              <th class="py-2 pr-3 font-medium">Atividade</th>
              <th class="py-2 pr-3 font-medium">Quando</th>
              <th class="py-2 pr-3 font-medium">Fila</th>
              <th class="py-2 pr-3 font-medium">Contrato</th>
              <th class="py-2 pr-3 font-medium">Próxima</th>
              <th class="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in tasks" :key="t.id" class="border-b border-default/60">
              <td class="py-3 pr-3">
                <p class="font-medium" :class="t.active ? 'text-highlighted' : 'text-muted line-through'">
                  {{ t.title }}
                </p>
                <p class="text-xs text-muted">solicitante: {{ t.customer_user_login }}</p>
              </td>
              <td class="py-3 pr-3 text-default">{{ t.schedule_label }}</td>
              <td class="py-3 pr-3 text-default">{{ t.znuny_queue_name || '—' }}</td>
              <td class="py-3 pr-3">
                <UBadge v-if="t.contract_id" color="primary" variant="subtle" size="sm">consome</UBadge>
                <span v-else class="text-xs text-muted">não consome</span>
              </td>
              <td class="py-3 pr-3 text-default">{{ t.next_occurrence ?? '—' }}</td>
              <td class="py-3 text-right">
                <div class="flex justify-end gap-1">
                  <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-pencil" @click="openEdit(t)">
                    Editar
                  </UButton>
                  <UButton
                    size="xs"
                    variant="ghost"
                    :color="t.active ? 'error' : 'success'"
                    :icon="t.active ? 'i-lucide-pause' : 'i-lucide-play'"
                    @click="toggleActive(t)"
                  >
                    {{ t.active ? 'Pausar' : 'Retomar' }}
                  </UButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- agenda -->
    <section v-else>
      <UCard v-if="!grouped.length" class="text-sm text-muted">
        Nada agendado nos próximos 30 dias.
      </UCard>
      <div v-else class="space-y-4">
        <UCard v-for="g in grouped" :key="g.date" :ui="{ body: 'space-y-2' }">
          <p class="font-display text-sm font-bold capitalize text-highlighted">
            {{ dateLabel(g.date) }}
          </p>
          <div v-for="e in g.items" :key="`${e.task_id}-${e.date}`" class="flex items-center justify-between gap-3">
            <span class="text-sm text-default">{{ e.title }}</span>
            <UBadge v-if="e.znuny_ticket_id" color="success" variant="subtle" size="sm">
              chamado #{{ e.znuny_ticket_id }}
            </UBadge>
            <span v-else class="text-xs text-muted">ainda não aberto</span>
          </div>
        </UCard>
      </div>
    </section>

    <UModal v-model:open="open" :title="editingId ? 'Editar atividade' : 'Nova atividade'">
      <template #body>
        <div class="space-y-4">
          <UAlert
            v-if="formErrors.length"
            color="error" variant="soft" icon="i-lucide-alert-triangle"
            title="Corrija os itens abaixo"
          >
            <template #description>
              <ul class="list-disc space-y-0.5 pl-5">
                <li v-for="e in formErrors" :key="e">{{ e }}</li>
              </ul>
            </template>
          </UAlert>
          <UAlert v-if="saveError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="saveError" />

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Título" required class="sm:col-span-2">
              <UInput v-model="draft.title" placeholder="Verificação de backup" />
            </UFormField>
            <UFormField label="Descrição" class="sm:col-span-2">
              <UTextarea v-model="draft.body" :rows="3" placeholder="O que o técnico deve fazer." />
            </UFormField>
            <UFormField label="Frequência" required>
              <USelect v-model="draft.frequency" :items="FREQUENCIES" />
            </UFormField>
            <UFormField v-if="draft.frequency === 'weekly'" label="Dia da semana" required>
              <USelect v-model="draft.weekday" :items="WEEKDAYS" />
            </UFormField>
            <UFormField v-else-if="draft.frequency === 'monthly'" label="Dia do mês" required>
              <UInput v-model.number="draft.day_of_month" type="number" :min="1" :max="31" />
            </UFormField>
            <div v-else />
            <UFormField label="Horário" required>
              <UInput v-model="draft.at_time" placeholder="08:00" />
            </UFormField>
            <UFormField label="Início" required>
              <UInput v-model="draft.starts_on" type="date" />
            </UFormField>
            <UFormField label="Fim (opcional)">
              <UInput v-model="draft.ends_on" type="date" />
            </UFormField>
            <UFormField label="Fila">
              <UInput v-model="draft.znuny_queue_name" placeholder="Preventivos" />
            </UFormField>
            <UFormField label="Solicitante" required help="Quem figura como autor do chamado.">
              <UInput v-model="draft.customer_user_login" placeholder="mariana.bianchi" />
            </UFormField>
            <UFormField label="Contrato" class="sm:col-span-2" :help="CONTRACT_HINT">
              <USelect v-model="draft.contract_id" :items="contractOptions" />
            </UFormField>
            <UAlert
              v-if="monthWarning"
              class="sm:col-span-2"
              color="warning" variant="soft" icon="i-lucide-calendar-x"
              :title="monthWarning"
            />
            <UFormField class="sm:col-span-2">
              <UCheckbox v-model="draft.active" label="Ativa (gera chamados automaticamente)" />
            </UFormField>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="ghost" color="neutral" :disabled="saving" @click="open = false">Cancelar</UButton>
          <UButton color="primary" :loading="saving" @click="save">Salvar</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
