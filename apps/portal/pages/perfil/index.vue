<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

// #3 V3 — dados da sessão (read-only) + preferências (editável, salva de
// verdade em PUT /api/portal/me/preferences). O seletor de tema também
// comanda o modo de cor do portal (@nuxtjs/color-mode), ao vivo.
definePageMeta({ middleware: 'auth' })

interface Preferences {
  theme: 'light' | 'dark' | 'system'
  email_notifications: boolean
  sla_alerts: boolean
  ticket_updates: boolean
  contract_alerts: boolean
  invoice_alerts: boolean
  weekly_report: boolean
}

const ROLE_LABEL: Record<string, string> = { admin: 'Administrador', helpdesk: 'Helpdesk' }
function roleLabel(role: string | undefined): string {
  if (!role) return '—'
  return ROLE_LABEL[role] ?? role
}

const THEME_OPTIONS = [
  { value: 'light', label: 'Claro' },
  { value: 'system', label: 'Sistema' },
  { value: 'dark', label: 'Escuro' },
] as const

const headers = useSidecarHeaders()
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')
const { data: me } = await useMe()
const colorMode = useColorMode()

const { data: prefs, pending, refresh } = await useAsyncData('me-preferences', () =>
  $fetch<Preferences | null>('/api/portal/me/preferences', { headers }).catch(() => null))

const loadFailed = computed(() => !pending.value && prefs.value === null)

// Rascunho editável — só é enviado ao backend ao clicar "Salvar".
const form = reactive<Preferences>({
  theme: 'system',
  email_notifications: true,
  sla_alerts: true,
  ticket_updates: true,
  contract_alerts: true,
  invoice_alerts: true,
  weekly_report: false,
})
let hydrated = false
watch(prefs, (v) => {
  if (!v) return
  Object.assign(form, v)
  hydrated = true
}, { immediate: true })

// O seletor também reflete/define o modo de cor do portal ao vivo (só depois
// de hidratar do backend — evita sobrescrever a preferência já persistida
// pelo cookie/localStorage do color-mode antes do fetch responder).
watch(() => form.theme, (t) => {
  if (!hydrated) return
  colorMode.preference = t
})

const saving = ref(false)
const saveError = ref<string | null>(null)
const saveOk = ref(false)

async function save() {
  saving.value = true
  saveError.value = null
  saveOk.value = false
  const res = await $fetch<Preferences>('/api/portal/me/preferences', {
    method: 'PUT',
    body: { ...form },
  }).catch(() => null)
  saving.value = false
  if (res === null) {
    saveError.value = 'Não foi possível salvar as preferências. Tente novamente.'
    return
  }
  Object.assign(form, res)
  saveOk.value = true
  await refresh()
}
</script>

<template>
  <div class="mx-auto max-w-2xl px-5 py-8">
    <header class="mb-8">
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Meu perfil
      </h1>
      <p class="mt-1 text-sm text-muted">
        Seus dados de acesso e as suas preferências de notificação.
      </p>
    </header>

    <!-- Dados da sessão (read-only) -->
    <UCard class="mb-6">
      <template #header>
        <p class="font-display text-base font-semibold text-highlighted">Meus dados</p>
      </template>
      <dl class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <dt class="text-xs font-medium uppercase tracking-wide text-dimmed">Nome</dt>
          <dd class="mt-0.5 text-sm text-default">{{ me?.display_name ?? '—' }}</dd>
        </div>
        <div>
          <dt class="text-xs font-medium uppercase tracking-wide text-dimmed">Login</dt>
          <dd class="mt-0.5 text-sm text-default">{{ me?.customer_login ?? '—' }}</dd>
        </div>
        <div>
          <dt class="text-xs font-medium uppercase tracking-wide text-dimmed">Papel</dt>
          <dd class="mt-0.5 text-sm text-default">{{ roleLabel(me?.role) }}</dd>
        </div>
        <div>
          <dt class="text-xs font-medium uppercase tracking-wide text-dimmed">Empresa</dt>
          <dd class="mt-0.5 text-sm text-default">{{ tenantName }}</dd>
        </div>
      </dl>
    </UCard>

    <!-- Loading das preferências -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 3" :key="n" class="h-14 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-4 py-10">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-error/10 text-error">
          <UIcon name="i-lucide-cloud-off" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar as preferências</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            As preferências estão indisponíveis no momento. Tente novamente em instantes.
          </p>
        </div>
        <UButton color="neutral" variant="subtle" icon="i-lucide-rotate-cw" label="Tentar novamente" @click="refresh()" />
      </div>
    </UCard>

    <!-- Preferências (editável) -->
    <UCard v-else>
      <template #header>
        <p class="font-display text-base font-semibold text-highlighted">Preferências</p>
      </template>

      <div class="space-y-6">
        <UFormField label="Tema" help="Define a aparência do portal neste navegador.">
          <div class="inline-flex items-center gap-1 rounded-lg border border-default bg-default p-1" role="group" aria-label="Tema">
            <button
              v-for="o in THEME_OPTIONS"
              :key="o.value"
              type="button"
              class="rounded-md px-3 py-1.5 text-sm font-medium transition"
              :class="form.theme === o.value ? 'bg-elevated text-highlighted' : 'text-muted hover:text-highlighted'"
              @click="form.theme = o.value"
            >
              {{ o.label }}
            </button>
          </div>
        </UFormField>

        <div class="space-y-4 border-t border-default pt-5">
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium text-default">Notificações por e-mail</p>
              <p class="text-xs text-muted">Receber um e-mail para cada notificação relevante.</p>
            </div>
            <USwitch v-model="form.email_notifications" />
          </div>
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium text-default">Alertas de SLA</p>
              <p class="text-xs text-muted">Avisos de SLA em risco ou estourado.</p>
            </div>
            <USwitch v-model="form.sla_alerts" />
          </div>
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium text-default">Atualizações de chamado</p>
              <p class="text-xs text-muted">Novas respostas e mudanças de status nos seus chamados.</p>
            </div>
            <USwitch v-model="form.ticket_updates" />
          </div>
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium text-default">Alertas de contrato</p>
              <p class="text-xs text-muted">Saldo crítico e avisos de renovação de contrato.</p>
            </div>
            <USwitch v-model="form.contract_alerts" />
          </div>
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium text-default">Alertas de fatura</p>
              <p class="text-xs text-muted">Aviso quando uma nova fatura for emitida.</p>
            </div>
            <USwitch v-model="form.invoice_alerts" />
          </div>
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium text-default">Relatório semanal</p>
              <p class="text-xs text-muted">Resumo semanal de chamados e consumo por e-mail.</p>
            </div>
            <USwitch v-model="form.weekly_report" />
          </div>
        </div>

        <div class="flex items-center gap-3 border-t border-default pt-5">
          <UButton color="primary" icon="i-lucide-save" label="Salvar preferências" :loading="saving" @click="save" />
          <p v-if="saveOk" class="text-sm text-success">Preferências salvas.</p>
          <p v-if="saveError" class="text-sm text-error">{{ saveError }}</p>
        </div>
      </div>
    </UCard>
  </div>
</template>
