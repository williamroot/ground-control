<script setup lang="ts">
// Calendário do Znuny — jornada de trabalho e feriados (Spec #4, Bloco D).
// A tela de MAIOR RISCO do console: grava direto no SysConfig do Znuny
// (TimeWorkingHours / TimeVacationDays / TimeVacationDaysOneTime) e dispara
// um deploy de configuração — um erro aqui afeta a INSTÂNCIA inteira, não só
// esta tela. Por isso: confirmação explícita com resumo do que muda antes de
// gravar, 422 tratado mostrando o motivo (nunca erro cru), e se a gravação
// falhar o operador precisa saber que NADA foi alterado (o sidecar libera o
// lock e não aplica parcial) e que pode tentar de novo com segurança.
import type {
  CalendarPayload,
  OneTimeHoliday,
  RecurringHoliday,
  WorkingGrid,
} from '../../composables/useWorkingHours'
import {
  CALENDAR_OPTIONS,
  emptyGrid,
  gridToPayload,
  oneTimeToPayload,
  parseCalendarErrors,
  payloadToGrid,
  payloadToOneTime,
  payloadToRecurring,
  recurringToPayload,
  summarizeCalendarChanges,
  validateCalendarPayload,
  weeklyTotalHours,
} from '../../composables/useWorkingHours'
import HoursGrid from '../../components/calendar/HoursGrid.vue'
import OneTimeHolidayEditor from '../../components/calendar/OneTimeHolidayEditor.vue'
import RecurringHolidayEditor from '../../components/calendar/RecurringHolidayEditor.vue'

definePageMeta({ middleware: 'admin-auth' })

interface CalendarResponse {
  calendar: string
  time_working_hours: Record<string, number[]>
  time_vacation_days: Record<string, Record<string, string>>
  time_vacation_days_one_time: Record<string, Record<string, Record<string, string>>>
}

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const selectedCalendar = ref('')

const { data, pending, refresh } = await useAsyncData<CalendarResponse | null>(
  'znuny-calendar',
  () => $fetch<CalendarResponse | null>('/api/admin/znuny/calendar', {
    headers,
    query: { calendar: selectedCalendar.value },
  }).catch(() => null),
  { watch: [selectedCalendar] },
)

const loadFailed = computed(() => !pending.value && data.value === null)

const activeTab = ref<'jornada' | 'feriados'>('jornada')
const tabs = [
  { label: 'Jornada de trabalho', value: 'jornada', slot: 'jornada' },
  { label: 'Feriados', value: 'feriados', slot: 'feriados' },
]

const grid = ref<WorkingGrid>(emptyGrid())
const recurring = ref<RecurringHoliday[]>([])
const oneTime = ref<OneTimeHoliday[]>([])

// Snapshot do que está gravado no Znuny agora — usado para o diff do resumo
// de confirmação e para saber se há algo pendente de salvar.
const loadedPayload = ref<CalendarPayload | null>(null)

watch(data, (d) => {
  if (!d) return
  grid.value = payloadToGrid(d.time_working_hours)
  recurring.value = payloadToRecurring(d.time_vacation_days)
  oneTime.value = payloadToOneTime(d.time_vacation_days_one_time)
  loadedPayload.value = {
    calendar: d.calendar ?? selectedCalendar.value,
    time_working_hours: d.time_working_hours ?? {},
    time_vacation_days: d.time_vacation_days ?? {},
    time_vacation_days_one_time: d.time_vacation_days_one_time ?? {},
  }
}, { immediate: true })

const isEmpty = computed(() => {
  if (!data.value) return false
  return weeklyTotalHours(grid.value) === 0 && recurring.value.length === 0 && oneTime.value.length === 0
})

const draftPayload = computed<CalendarPayload>(() => ({
  calendar: selectedCalendar.value,
  time_working_hours: gridToPayload(grid.value),
  time_vacation_days: recurringToPayload(recurring.value),
  time_vacation_days_one_time: oneTimeToPayload(oneTime.value),
}))

const clientErrors = computed(() => validateCalendarPayload(draftPayload.value))

const isDirty = computed(() => {
  if (!loadedPayload.value) return false
  return JSON.stringify(draftPayload.value) !== JSON.stringify(loadedPayload.value)
})

const summary = computed(() => (loadedPayload.value
  ? summarizeCalendarChanges(loadedPayload.value, draftPayload.value)
  : null))

const calendarLabel = computed(() =>
  CALENDAR_OPTIONS.find(o => o.value === selectedCalendar.value)?.label ?? 'Padrão')

const confirmOpen = ref(false)
const saving = ref(false)
const saveErrors = ref<string[]>([])
const saveFailed = ref(false)

function openConfirm() {
  saveErrors.value = []
  saveFailed.value = false
  if (clientErrors.value.length > 0 || !isDirty.value) return
  confirmOpen.value = true
}

async function confirmSave() {
  saving.value = true
  saveErrors.value = []
  saveFailed.value = false
  try {
    await $fetch('/api/admin/znuny/calendar', {
      method: 'PUT',
      body: draftPayload.value,
    })
    confirmOpen.value = false
    toast.add({
      title: 'Calendário salvo no Znuny',
      description: 'Deploy de configuração disparado — a nova jornada já vale para o cálculo de SLA de todos os chamados.',
      color: 'success',
    })
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: unknown } }
    saveFailed.value = true
    if (err.statusCode === 422) {
      saveErrors.value = parseCalendarErrors(err.data?.detail)
    }
    else if (err.statusCode === 503) {
      saveErrors.value = ['O Znuny está indisponível no momento.']
    }
    else {
      saveErrors.value = ['Falha inesperada ao gravar no Znuny.']
    }
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <header class="mb-4">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Calendário — jornada e feriados
      </h1>
      <p class="mt-1 text-sm text-muted">
        Jornada de trabalho e feriados que o Znuny usa para calcular o SLA de todos os chamados.
      </p>
    </header>

    <UAlert
      color="warning"
      variant="soft"
      icon="i-lucide-shield-alert"
      title="Esta tela grava direto na configuração do Znuny"
      description="Salvar aqui muda o SysConfig e dispara um deploy de configuração que vale para a instância inteira — não só para este calendário. Confira o resumo antes de confirmar."
      class="mb-6"
    />

    <div class="mb-6 max-w-xs">
      <label class="mb-1 block text-xs font-medium text-muted">Calendário</label>
      <USelect v-model="selectedCalendar" :items="CALENDAR_OPTIONS" :disabled="pending" />
    </div>

    <!-- Carregando -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 4" :key="n" class="h-16 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar</p>
        <p class="max-w-sm text-sm text-muted">
          Falha ao buscar o calendário "{{ calendarLabel }}" no Znuny. Tente novamente.
        </p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refresh()">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <template v-else>
      <UAlert
        v-if="isEmpty"
        color="neutral"
        variant="soft"
        icon="i-lucide-info"
        title="Calendário ainda sem configuração"
        description="Este calendário não tem nenhuma hora útil nem feriado cadastrado. Configure abaixo e salve quando terminar."
        class="mb-6"
      />

      <UTabs v-model="activeTab" :items="tabs">
        <template #jornada>
          <UCard class="mt-4" :ui="{ body: 'space-y-4' }">
            <HoursGrid v-model="grid" />
          </UCard>
        </template>
        <template #feriados>
          <div class="mt-4 grid gap-6 lg:grid-cols-2">
            <UCard :ui="{ body: 'space-y-4' }">
              <h2 class="font-display text-sm font-semibold uppercase tracking-wide text-dimmed">
                Recorrentes (repetem todo ano)
              </h2>
              <RecurringHolidayEditor v-model="recurring" />
            </UCard>
            <UCard :ui="{ body: 'space-y-4' }">
              <h2 class="font-display text-sm font-semibold uppercase tracking-wide text-dimmed">
                De data específica
              </h2>
              <OneTimeHolidayEditor v-model="oneTime" />
            </UCard>
          </div>
        </template>
      </UTabs>

      <UAlert
        v-if="clientErrors.length > 0"
        color="error"
        variant="soft"
        icon="i-lucide-alert-triangle"
        title="Corrija antes de salvar"
        class="mt-6"
      >
        <template #description>
          <ul class="list-disc space-y-0.5 pl-4">
            <li v-for="(e, i) in clientErrors" :key="i">{{ e }}</li>
          </ul>
        </template>
      </UAlert>

      <div class="mt-6 flex items-center gap-3">
        <UButton
          color="primary"
          icon="i-lucide-check"
          :disabled="!isDirty || clientErrors.length > 0"
          @click="openConfirm"
        >
          Salvar calendário
        </UButton>
        <span v-if="!isDirty" class="text-xs text-dimmed">Nenhuma alteração pendente.</span>
      </div>
    </template>

    <!-- Confirmação: resumo do que muda antes de gravar no Znuny -->
    <UModal
      v-model:open="confirmOpen"
      title="Confirmar gravação no Znuny"
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert
            color="warning"
            variant="soft"
            icon="i-lucide-shield-alert"
            title="Isto grava no SysConfig e dispara um deploy de configuração."
            description="O cálculo de SLA de TODOS os chamados passa a usar esta jornada a partir de agora."
          />

          <div v-if="summary" data-testid="change-summary" class="space-y-1.5 rounded-lg border border-default bg-elevated/50 p-3 text-sm text-default">
            <p>Calendário: <span class="font-medium">{{ calendarLabel }}</span></p>
            <p>
              Horas úteis por semana:
              <span class="font-medium">{{ summary.weeklyHoursBefore }}h → {{ summary.weeklyHoursAfter }}h</span>
              <span v-if="!summary.weeklyHoursChanged" class="text-dimmed"> (sem mudança)</span>
            </p>
            <p v-if="summary.recurringAdded || summary.recurringRemoved || summary.recurringChanged">
              Feriados recorrentes:
              <span v-if="summary.recurringAdded">+{{ summary.recurringAdded }} novo(s) </span>
              <span v-if="summary.recurringRemoved">-{{ summary.recurringRemoved }} removido(s) </span>
              <span v-if="summary.recurringChanged">{{ summary.recurringChanged }} alterado(s)</span>
            </p>
            <p v-if="summary.oneTimeAdded || summary.oneTimeRemoved || summary.oneTimeChanged">
              Feriados de data específica:
              <span v-if="summary.oneTimeAdded">+{{ summary.oneTimeAdded }} novo(s) </span>
              <span v-if="summary.oneTimeRemoved">-{{ summary.oneTimeRemoved }} removido(s) </span>
              <span v-if="summary.oneTimeChanged">{{ summary.oneTimeChanged }} alterado(s)</span>
            </p>
          </div>

          <UAlert
            v-if="saveErrors.length > 0"
            color="error"
            variant="soft"
            icon="i-lucide-alert-triangle"
            :title="saveFailed ? 'Não foi salvo — nada foi alterado' : 'Erro'"
          >
            <template #description>
              <ul class="list-disc space-y-0.5 pl-4">
                <li v-for="(e, i) in saveErrors" :key="i">{{ e }}</li>
              </ul>
              <p class="mt-2 text-xs">O lock do Znuny foi liberado. Corrija e tente novamente com segurança.</p>
            </template>
          </UAlert>
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="saving" @click="confirmOpen = false" />
        <UButton
          label="Confirmar e gravar no Znuny"
          color="warning"
          icon="i-lucide-check"
          :loading="saving"
          @click="confirmSave"
        />
      </template>
    </UModal>
  </div>
</template>
