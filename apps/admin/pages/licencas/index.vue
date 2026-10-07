<script setup lang="ts">
import type { AgentLicense, LicenseOverview, ModuleOption } from '~/composables/useLicensing'
import {
  agentSelectOptions,
  enforcementNotice,
  moduleLabel,
  normalizeZnunyAgents,
  seatTone,
  seatUsagePercent,
  sidecarErrorMessage,
  validateAssignment,
  validateSeats,
} from '~/composables/useLicensing'

// R16 — o quadro de licenças da operação.
//
// *"Hoje tem sete usuários ativos, a gente tem um total de nove. Total de
// clientes cadastrados, 60. Contratos ativos, 43. […] Isso aqui impacta no
// faturamento da plataforma para a gente."* (09:24)
//
// Dado da Gerti sobre a Gerti: nada aqui existe no portal do cliente, e as
// tabelas por baixo nem são legíveis pela conexão que o atende.
definePageMeta({ middleware: 'admin-auth' })

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const { data: overview, refresh: refreshOverview } = await useAsyncData('licensing-overview', () =>
  $fetch<LicenseOverview | null>('/api/admin/licensing/overview', { headers }).catch(() => null))
const { data: licenses, refresh: refreshLicenses } = await useAsyncData('licensing-agents', () =>
  $fetch<AgentLicense[] | null>('/api/admin/licensing/agents', { headers }).catch(() => null))
const { data: modules } = await useAsyncData('licensing-modules', () =>
  $fetch<ModuleOption[] | null>('/api/admin/licensing/modules', { headers }).catch(() => null))
// Agentes reais do Znuny — a licença só pode ir para quem existe (teste V01, F5).
const {
  data: znunyAgents,
  pending: agentsPending,
  refresh: refreshAgents,
} = await useAsyncData('licensing-znuny-agents', () =>
  $fetch<unknown>('/api/admin/znuny/agents', { headers }).catch(() => null))

const seats = ref(0)
const savingSeats = ref(false)
const login = ref('')
const chosen = ref<string[]>([])
const savingAssign = ref(false)

watchEffect(() => {
  if (overview.value) seats.value = overview.value.seats_total
})

const notice = computed(() => (overview.value ? enforcementNotice(overview.value) : null))
const usage = computed(() => (overview.value ? seatUsagePercent(overview.value) : 0))
const tone = computed(() => (overview.value ? seatTone(overview.value) : 'neutral'))
// Erro só depois que a pessoa mexeu: um formulário recém-aberto mostrando
// "Informe o login do agente" em vermelho parece defeito, não orientação.
const touchedLogin = ref(false)
watch(login, () => { touchedLogin.value = true })

const seatErrors = computed(() =>
  overview.value ? validateSeats(seats.value, overview.value) : [])
const existing = computed(() =>
  (licenses.value ?? []).find(l => l.agent_login === login.value.trim()) ?? null)
const assignErrors = computed(() =>
  overview.value ? validateAssignment(login.value, chosen.value, overview.value, existing.value) : [])
const moduleOptions = computed(() => modules.value ?? [])

const agentsFailed = computed(() => !agentsPending.value && znunyAgents.value === null)
const agentList = computed(() => normalizeZnunyAgents(znunyAgents.value))
const agentOptions = computed(() => agentSelectOptions(agentList.value, licenses.value, login.value))

// Escolher quem já tem licença é editar: traz os módulos dele.
watch(existing, (row) => {
  if (row) chosen.value = [...row.modules]
})

function fmt(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString('pt-BR') : '—'
}

function toggle(value: string) {
  chosen.value = chosen.value.includes(value)
    ? chosen.value.filter(m => m !== value)
    : [...chosen.value, value]
}

function edit(row: AgentLicense) {
  login.value = row.agent_login
  chosen.value = [...row.modules]
}

async function saveSeats() {
  if (seatErrors.value.length) return
  savingSeats.value = true
  try {
    await $fetch('/api/admin/licensing/seats', {
      method: 'PUT',
      body: { seats_total: seats.value },
    })
    toast.add({ title: 'Total de licenças atualizado', color: 'success' })
    await refreshOverview()
  }
  catch (e) {
    toast.add({ title: 'Não foi possível salvar', description: sidecarErrorMessage(e), color: 'error' })
  }
  finally {
    savingSeats.value = false
  }
}

async function assign() {
  if (assignErrors.value.length) return
  savingAssign.value = true
  try {
    await $fetch('/api/admin/licensing/agents', {
      method: 'PUT',
      body: { agent_login: login.value.trim(), modules: chosen.value },
    })
    toast.add({ title: `Licença de ${login.value.trim()} salva`, color: 'success' })
    login.value = ''
    chosen.value = []
    await Promise.all([refreshOverview(), refreshLicenses()])
  }
  catch (e) {
    // O 422 do sidecar traz a contagem ("7 de 9 em uso"), o agente que não
    // existe ou a lista de módulos válidos — repassar a mensagem dele, como
    // veio, é o que dá ao operador o próximo passo.
    toast.add({ title: 'Licença recusada', description: sidecarErrorMessage(e), color: 'error' })
  }
  finally {
    savingAssign.value = false
  }
}

// Revogar tira o acesso do agente aos módulos — destrutivo, então confirma
// num diálogo com o login em destaque antes do DELETE.
const revokeTarget = ref<AgentLicense | null>(null)
const revokeOpen = computed({
  get: () => revokeTarget.value !== null,
  set: (open: boolean) => { if (!open && !revoking.value) revokeTarget.value = null },
})
const revoking = ref(false)

function askRevoke(row: AgentLicense) {
  revokeTarget.value = row
}

async function confirmRevoke() {
  const row = revokeTarget.value
  if (!row) return
  revoking.value = true
  try {
    await $fetch(`/api/admin/licensing/agents/${encodeURIComponent(row.agent_login)}`, {
      method: 'DELETE',
    })
    toast.add({ title: `Licença de ${row.agent_login} revogada`, color: 'neutral' })
    revokeTarget.value = null
    await Promise.all([refreshOverview(), refreshLicenses()])
  }
  catch (e) {
    toast.add({ title: 'Falha ao revogar', description: sidecarErrorMessage(e), color: 'error' })
  }
  finally {
    revoking.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-5 py-10">
    <header class="mb-6">
      <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
        Licenças
      </h1>
      <p class="mt-1 text-sm text-muted">
        Agentes contratados, clientes e contratos ativos. Este número impacta o faturamento
        da plataforma.
      </p>
    </header>

    <UAlert
      v-if="notice"
      class="mb-6"
      color="warning"
      variant="soft"
      icon="i-lucide-shield-off"
      title="Os módulos ainda não restringem o acesso"
      :description="notice"
    />

    <!-- O quadrinho -->
    <div v-if="overview" class="mb-6 grid gap-4 sm:grid-cols-3">
      <UCard>
        <p class="text-xs uppercase text-muted">Agentes licenciados</p>
        <p class="mt-1 font-display text-2xl font-extrabold text-highlighted">
          {{ overview.seats_used }}<span class="text-muted"> de {{ overview.seats_total }}</span>
        </p>
        <UProgress :model-value="usage" :color="tone === 'neutral' ? 'primary' : tone" class="mt-2" />
        <p class="mt-1 text-xs" :class="tone === 'error' ? 'text-error' : 'text-muted'">
          {{ overview.seats_free }} livre(s)
        </p>
      </UCard>
      <UCard>
        <p class="text-xs uppercase text-muted">Clientes cadastrados</p>
        <p class="mt-1 font-display text-2xl font-extrabold text-highlighted">
          {{ overview.tenants_total }}
        </p>
      </UCard>
      <UCard>
        <p class="text-xs uppercase text-muted">Contratos ativos</p>
        <p class="mt-1 font-display text-2xl font-extrabold text-highlighted">
          {{ overview.contracts_active }}
        </p>
      </UCard>
    </div>

    <!-- Total contratado -->
    <UCard class="mb-6">
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Total contratado</h2>
      </template>
      <div class="flex flex-wrap items-end gap-3">
        <UFormField label="Licenças de agente">
          <UInput v-model.number="seats" type="number" min="0" class="w-32" />
        </UFormField>
        <UButton
          :loading="savingSeats"
          :disabled="seatErrors.length > 0"
          icon="i-lucide-save"
          label="Salvar"
          @click="saveSeats"
        />
      </div>
      <ul v-if="seatErrors.length" class="mt-3 list-disc pl-5 text-sm text-error">
        <li v-for="err in seatErrors" :key="err">{{ err }}</li>
      </ul>
      <p class="mt-3 text-xs text-muted">
        Quem define o total é a Gerti — é ferramenta de gestão dela, não espelho de contrato
        externo. Toda mudança fica na auditoria.
      </p>
    </UCard>

    <!-- Atribuir -->
    <UCard class="mb-6">
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">
          {{ existing ? `Editar licença de ${existing.agent_login}` : 'Atribuir licença' }}
        </h2>
      </template>
      <UFormField label="Agente do Znuny">
        <div v-if="agentsPending" class="h-8 w-full animate-pulse rounded-md bg-elevated sm:w-96" />
        <div v-else-if="agentsFailed" class="flex flex-wrap items-center gap-2 py-1.5 text-sm text-error">
          Não foi possível carregar os agentes do Znuny.
          <UButton
            size="xs"
            variant="soft"
            color="primary"
            icon="i-lucide-refresh-cw"
            label="Tentar novamente"
            @click="refreshAgents()"
          />
        </div>
        <div v-else-if="agentOptions.length === 0" class="flex flex-wrap items-center gap-2 py-1.5 text-sm text-muted">
          Nenhum agente válido no Znuny.
          <UButton
            to="/znuny/agentes"
            size="xs"
            variant="soft"
            color="primary"
            icon="i-lucide-user-plus"
            label="Cadastrar agente"
          />
        </div>
        <!-- Sem placeholder com nome de gente: "georgia" em cinza parecia
             valor preenchido e o operador recebia "Informe o login". -->
        <USelectMenu
          v-else
          v-model="login"
          data-testid="license-agent-select"
          :items="agentOptions"
          value-key="value"
          placeholder="Escolha o agente"
          :search-input="{ placeholder: 'Buscar por nome ou login' }"
          class="w-full sm:w-96"
        />
      </UFormField>
      <div class="mt-4">
        <p class="mb-2 text-sm font-medium text-highlighted">Módulos</p>
        <div class="flex flex-wrap gap-2">
          <UButton
            v-for="m in moduleOptions"
            :key="m.value"
            size="sm"
            :color="chosen.includes(m.value) ? 'primary' : 'neutral'"
            :variant="chosen.includes(m.value) ? 'solid' : 'soft'"
            :icon="chosen.includes(m.value) ? 'i-lucide-check' : 'i-lucide-plus'"
            :label="m.label"
            @click="toggle(m.value)"
          />
        </div>
        <p class="mt-2 text-xs text-muted">
          Só os módulos que o produto tem hoje. WhatsApp e acesso remoto entram quando o
          recurso existir — botão que não faz nada é pior do que botão nenhum.
        </p>
      </div>
      <ul v-if="touchedLogin && assignErrors.length" class="mt-3 list-disc pl-5 text-sm text-error">
        <li v-for="err in assignErrors" :key="err">{{ err }}</li>
      </ul>
      <template #footer>
        <UButton
          :loading="savingAssign"
          :disabled="assignErrors.length > 0"
          icon="i-lucide-id-card"
          :label="existing ? 'Salvar licença' : 'Atribuir'"
          @click="assign"
        />
      </template>
    </UCard>

    <!-- Lista -->
    <UCard>
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Agentes</h2>
      </template>
      <p v-if="!licenses || licenses.length === 0" class="text-sm text-muted">
        Nenhuma licença atribuída ainda.
      </p>
      <table v-else class="w-full text-sm">
        <thead class="text-left text-xs uppercase text-muted">
          <tr>
            <th class="py-2">Agente</th>
            <th class="py-2">Módulos</th>
            <th class="py-2">Desde</th>
            <th class="py-2 text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in licenses" :key="row.agent_login" class="border-t border-default">
            <td class="py-2 font-medium text-highlighted">
              {{ row.agent_login }}
              <UBadge v-if="!row.active" color="neutral" variant="soft" size="sm" class="ml-1">
                revogada
              </UBadge>
            </td>
            <td class="py-2">
              <span v-if="!row.modules.length" class="text-muted">—</span>
              <UBadge
                v-for="m in row.modules"
                :key="m"
                color="primary"
                variant="soft"
                size="sm"
                class="mr-1"
              >
                {{ moduleLabel(m, moduleOptions) }}
              </UBadge>
            </td>
            <td class="py-2 text-muted">{{ fmt(row.assigned_at) }}</td>
            <td class="py-2">
              <div class="flex justify-end gap-2">
                <UButton
                  size="xs"
                  variant="soft"
                  icon="i-lucide-pencil"
                  label="Editar"
                  @click="edit(row)"
                />
                <UButton
                  v-if="row.active"
                  size="xs"
                  color="neutral"
                  variant="ghost"
                  icon="i-lucide-user-minus"
                  label="Revogar"
                  @click="askRevoke(row)"
                />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </UCard>

    <UModal
      v-model:open="revokeOpen"
      title="Revogar licença"
      :ui="{ footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-3 text-sm text-default">
          <p>
            Revogar a licença de
            <span class="font-mono font-semibold text-highlighted">{{ revokeTarget?.agent_login }}</span>?
          </p>
          <p class="text-muted">
            O agente perde os módulos licenciados (quando a exigência de licença está ligada) e a
            licença volta para o total livre. Dá para atribuir de novo depois, se houver licença
            disponível. Fica registrado na auditoria.
          </p>
        </div>
      </template>
      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="revoking" @click="revokeOpen = false" />
        <UButton
          :label="`Revogar ${revokeTarget?.agent_login ?? ''}`"
          color="error"
          icon="i-lucide-user-minus"
          :loading="revoking"
          data-testid="confirm-revoke"
          @click="confirmRevoke"
        />
      </template>
    </UModal>
  </div>
</template>
